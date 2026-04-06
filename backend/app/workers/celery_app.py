from __future__ import annotations

"""
Celery application instance.

Broker and result backend are both Redis, configured via REDIS_URL.
"""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "analyzer",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Retry connection to broker on startup
    broker_connection_retry_on_startup=True,
    # Task acknowledgement only after completion (at-least-once delivery)
    task_acks_late=True,
    # Prefetch one task at a time per worker to avoid starving other workers
    worker_prefetch_multiplier=1,
    # Retry policy for failed tasks
    task_default_retry_delay=30,
    task_max_retries=3,
)
