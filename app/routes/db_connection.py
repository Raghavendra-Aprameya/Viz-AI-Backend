from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from services import create_database_connections
from schemas import DBConnectionsRequest, DBConnectionResponse
from app.core.db import get_db

router = APIRouter()

@router.post("/databases/", response_model=List[DBConnectionResponse])
async def add_database_connections(
    data: DBConnectionsRequest,
    db: Session = Depends(get_db)
):
    return await create_database_connections(data, db)
