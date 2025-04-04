from fastapi import APIRouter, status, Response, Depends, Request, Path
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.db import get_db
from app.schemas import ProjectRequest,DBConnectionResponse,DBConnectionRequest, ConnectionRequest
from app.services.project import create_project
from app.utils.token_parser import parse_token
from app.services.db_connection import create_database_connection, get_connections


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


@backend_router.get("/connections/{project_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(parse_token)], response_model=dict)
async def get_connections_route(
    project_id: UUID = Path(..., description="Project ID to get connections for"),
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db)
):
    return await get_connections(project_id, request, response, db)