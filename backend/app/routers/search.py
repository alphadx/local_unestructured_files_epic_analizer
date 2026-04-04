from __future__ import annotations

from fastapi import APIRouter

from app.models.schemas import SearchRequest, SearchResponse
from app.services.search_service import search_corpus

router = APIRouter(prefix="/api/search", tags=["search"])


@router.post("", response_model=SearchResponse)
async def search(request: SearchRequest) -> SearchResponse:
    return search_corpus(request)
