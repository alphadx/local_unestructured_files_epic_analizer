import sys
import tempfile
import os
from pathlib import Path

import pytest
import pytest_asyncio

# Make sure the backend package is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

# ---------------------------------------------------------------------------
# In-memory SQLite database setup (file-based for stability across threads)
# ---------------------------------------------------------------------------

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base

# Use a temp file so connections from different event loops all see the same data.
_TEST_DB_FILE = os.path.join(tempfile.gettempdir(), "analyzer_pytest.db")
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{_TEST_DB_FILE}"

_test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
_TestSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def _create_test_tables() -> None:
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _get_test_db():
    """FastAPI dependency override: yield a SQLite in-memory session."""
    async with _TestSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """Create all SQLAlchemy tables in the test SQLite database once per session."""
    import asyncio

    # Remove stale DB from a previous run
    if os.path.exists(_TEST_DB_FILE):
        os.remove(_TEST_DB_FILE)

    asyncio.get_event_loop_policy().get_event_loop().run_until_complete(_create_test_tables())


@pytest.fixture(autouse=True)
def clean_tables():
    """Truncate all tables between tests using raw sqlite3 to avoid event-loop conflicts."""
    yield
    import sqlite3

    conn = sqlite3.connect(_TEST_DB_FILE)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(f"DELETE FROM {table.name}")
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()


@pytest.fixture(autouse=True)
def override_get_db():
    """Override the FastAPI get_db dependency and AsyncSessionLocal for every test to use SQLite."""
    from app.db.session import get_db
    from app.main import app
    import app.db.session as db_session
    import app.services.audit_log as audit_log_module

    _orig_session_local = db_session.AsyncSessionLocal

    # Redirect both the FastAPI dependency AND the module-level AsyncSessionLocal
    # (used by audit_log's fire-and-forget background tasks) to the test DB.
    app.dependency_overrides[get_db] = _get_test_db
    db_session.AsyncSessionLocal = _TestSessionLocal
    audit_log_module.AsyncSessionLocal = _TestSessionLocal  # type: ignore[attr-defined]

    yield

    app.dependency_overrides.clear()
    db_session.AsyncSessionLocal = _orig_session_local
    audit_log_module.AsyncSessionLocal = _orig_session_local  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def patch_celery_task(monkeypatch):
    """
    Replace the Celery task dispatch with a direct synchronous call so that
    pipeline jobs complete within the test without a running Redis/worker.

    ``_FakeTask.delay`` is called from within FastAPI's async context, so we
    cannot use ``asyncio.run()`` (which fails if a loop is already running).
    We spin up a daemon thread with its own event loop instead.
    """
    import asyncio
    import threading

    def _fake_delay(job_id: str, request_data: dict) -> None:
        """Run the pipeline in a fresh thread/event loop."""
        error: list = []

        def run_in_thread() -> None:
            # Create a fresh engine for this thread's event loop to avoid
            # aiosqlite connection pool issues across different event loops.
            from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine as _new_engine

            import app.services.job_manager as jm
            jm._redis = None  # type: ignore[attr-defined]

            from app.models.schemas import ScanRequest
            from app.services import job_manager

            request = ScanRequest(**request_data)

            async def _run():
                thread_engine = _new_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
                thread_session_factory = async_sessionmaker(bind=thread_engine, class_=AsyncSession, expire_on_commit=False)
                async with thread_session_factory() as test_db:
                    await job_manager.run_pipeline(job_id, request, db=test_db)
                await thread_engine.dispose()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_run())
            except Exception as exc:
                error.append(exc)
            finally:
                loop.close()
                asyncio.set_event_loop(None)

        t = threading.Thread(target=run_in_thread, daemon=True)
        t.start()
        t.join(timeout=60)
        if error:
            import traceback as tb
            tb.print_exception(type(error[0]), error[0], error[0].__traceback__)

    class _FakeTask:
        def delay(self, job_id, request_data):
            _fake_delay(job_id, request_data)

    try:
        import app.routers.jobs as jobs_router

        monkeypatch.setattr(jobs_router, "run_analysis_pipeline", _FakeTask())
    except Exception:
        pass
