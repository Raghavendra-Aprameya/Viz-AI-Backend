from fastapi import APIRouter, status, Response, Depends, Request,Path, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List
from app.core.db import get_db
from app.schemas import ProjectRequest,DBConnectionResponse,DBConnectionRequest,ConnectionRequest, ProjectsResponse,QueryRequest
from app.services.project import create_project, get_projects, list_all_roles_project
from app.utils.token_parser import parse_token,get_current_user
from app.services.db_connection import create_database_connection, get_connections
from app.services.userService import create_user_project, list_all_users_project
from app.schemas import CreateUserProjectRequest, CreateUserProjectResponse, ListAllUsersProjectResponse, ListAllRolesProjectResponse
from app.dependencies import get_db_session
from app.services import generate_charts_for_db

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
    return await create_database_connection(data, db,token_payload)

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

@backend_router.get("/projects/{project_id}/users", status_code=status.HTTP_200_OK, response_model=ListAllUsersProjectResponse)
async def list_all_users(
    project_id: UUID = Path(..., description="Project ID to list all users for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await list_all_users_project(project_id, db, token_payload)

@backend_router.get("/projects/{project_id}/roles", status_code=status.HTTP_200_OK, response_model=ListAllRolesProjectResponse)
async def list_all_roles(
    project_id: UUID = Path(..., description="Project ID to list all roles for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await list_all_roles_project(project_id, db, token_payload)

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
