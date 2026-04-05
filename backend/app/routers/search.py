from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import SearchRequest, SearchResponse
from app.services import audit_log
from app.services.search_service import search_corpus

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    result = search_corpus(request)
    audit_log.record(
        "search.executed",
        resource_type="search",
        job_id=request.job_id,
        query=request.query,
        total_results=result.total_results,
        scope=request.scope.value,
    )
    return result
