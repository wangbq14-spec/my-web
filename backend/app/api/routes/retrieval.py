from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.routes.auth import get_current_user
from app.db.session import get_db
from app.models.rag_query import RagQuery
from app.models.user import User
from app.rag.retrieval import retrieve
from app.schemas.retrieval import RetrievedChunkOut, RetrievalRequest

router = APIRouter()


@router.post("/search", response_model=list[RetrievedChunkOut])
def search_documents(
    request: RetrievalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RetrievedChunkOut]:
    results = retrieve(db, current_user.id, request.query, request.top_k)
    # Ops analytics: record only the fact that a retrieval happened (no content).
    db.add(RagQuery(user_id=current_user.id))
    db.commit()
    return results
