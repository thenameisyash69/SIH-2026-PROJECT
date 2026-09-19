from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app import schemas
from app.services.rag_engine import answer_query

router = APIRouter(prefix="/chatbot", tags=["chatbot"])


@router.post("/query", response_model=schemas.ChatResponse)
def query_chatbot(payload: schemas.ChatRequest, db: Session = Depends(get_db)):
    return answer_query(payload.question, db)
