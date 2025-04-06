from fastapi import APIRouter, status, Response, Depends, Request,HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.db import get_db
from app.schemas import ProjectRequest,DBConnectionResponse,DBConnectionRequest,QueryRequest
from app.services.project import create_project
from app.utils.token_parser import parse_token
from app.services.db_connection import create_database_connection
from app.services import generate_charts_for_db
from app.dependencies import get_db_session
from uuid import UUID


backend_router = APIRouter(prefix="/api/v1/backend", tags=["backend"])

@backend_router.post("/create-project", status_code=status.HTTP_201_CREATED, dependencies=[Depends(parse_token)])
async def create_project_route(project: ProjectRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    return await create_project(project, request, response, db)

@backend_router.post("/database/", response_model=DBConnectionResponse)
async def add_database_connection(
    data: DBConnectionRequest,
    db: Session = Depends(get_db)
):
    return await create_database_connection(data, db)


@backend_router.post("/generate_charts/{db_id}")
async def generate_charts(
    db_id: UUID,
    request: QueryRequest,
    db: Session = Depends(get_db_session)
):
    llm_url = "http://llm-service:8001/generate-query"  # Passed here instead of hardcoding
    try:
        charts = await generate_charts_for_db(db, db_id, request, llm_url)
        return {"success": True, "generated_charts": [chart.id for chart in charts]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
