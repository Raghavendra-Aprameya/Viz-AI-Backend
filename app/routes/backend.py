from fastapi import APIRouter, status, Response, Depends, Request, Path
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.db import get_db
from app.schemas import ProjectRequest,DBConnectionResponse,DBConnectionRequest, ConnectionRequest, ProjectsResponse
from app.services.project import create_project, get_projects
from app.utils.token_parser import get_current_user
from app.services.db_connection import create_database_connection, get_connections
from app.services.userService import create_user_project
from app.schemas import CreateUserProjectRequest, CreateUserProjectResponse

backend_router = APIRouter(prefix="/api/v1/backend", tags=["backend"])

@backend_router.post("/create-project", status_code=status.HTTP_201_CREATED)
async def create_project_route(
    project: ProjectRequest, 
    request: Request, 
    response: Response, 
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await create_project(project, request, response, db, token_payload)

@backend_router.post("/database/", response_model=DBConnectionResponse)
async def add_database_connection(
    data: DBConnectionRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await create_database_connection(data, db, token_payload)


@backend_router.get("/connections/{project_id}", status_code=status.HTTP_200_OK, response_model=dict)
async def get_connections_route(
    project_id: UUID = Path(..., description="Project ID to get connections for"),
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await get_connections(project_id, request, response, db, token_payload)

@backend_router.get("/projects", status_code=status.HTTP_200_OK, response_model=ProjectsResponse)
async def get_projects_route(
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await get_projects(request, response, db, token_payload)

@backend_router.post("/projects/{project_id}/users", status_code=status.HTTP_201_CREATED, response_model=CreateUserProjectResponse)
async def add_user_project(
    project_id: UUID = Path(..., description="Project ID to add user to"),
    data: CreateUserProjectRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await create_user_project(data, db, token_payload, project_id)
