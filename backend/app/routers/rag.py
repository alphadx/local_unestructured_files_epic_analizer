from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import RagQueryRequest, RagQueryResponse
from app.services.rag_service import query_rag

router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post("/query", response_model=RagQueryResponse)
def rag_query(request: RagQueryRequest) -> RagQueryResponse:
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    return query_rag(request)
