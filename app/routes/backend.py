from fastapi import APIRouter, status, Response, Depends, Request,Path, HTTPException,Body
from sqlalchemy.orm import Session
from sqlalchemy import select
from uuid import UUID
from typing import List
from app.core.db import get_db
from app.schemas import ProjectRequest,DBConnectionRequest, ProjectsResponse,QueryRequest,Nl2SQLChatRequest
from app.services.project import create_project, get_projects, list_all_roles_project
from app.utils.token_parser import parse_token,get_current_user
from app.services.db_connection import create_database_connection
from app.services.userService import create_user_project, list_all_users_project
from app.schemas import CreateUserProjectRequest, CreateUserProjectResponse, ListAllUsersProjectResponse, ListAllRolesProjectResponse
from app.core.db import get_db
from app.services.generate_queries import generate_and_store_charts
from app.services.nl2sql import generate_nl_sql_and_save
from app.models.schema_models import UserProjectRoleModel

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

from fastapi import Path

@backend_router.post("/database/{project_id}")
async def add_database_connection(
    data: DBConnectionRequest,
    project_id: UUID = Path(..., description="Project ID to link this DB connection to"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await create_database_connection(project_id, data, db, token_payload)



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

@backend_router.post("/generate_charts/{project_id}/{dashboard_id}")
async def generate_charts(
    project_id: UUID,
    dashboard_id: UUID,
    request: QueryRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    user_id_str = token_payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user_id = UUID(user_id_str)

    user_project_role =  db.execute(
        select(UserProjectRoleModel).filter_by(user_id=user_id, project_id=project_id)
    )
    user_project_role = user_project_role.scalar_one_or_none()
    if not user_project_role:
        raise HTTPException(status_code=403, detail="Access denied: User not in project")

    role = user_project_role.role.name.lower()
    if role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can generate charts")

    try:
        charts = await generate_and_store_charts(db,dashboard_id,project_id, request)
        return {"success": True, "generated_chart_ids": [chart.id for chart in charts]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@backend_router.post("/nl2sql/generate-and-save")
async def generate_and_save_route(
    data: Nl2SQLChatRequest = Body(...),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    user_id_str = token_payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user_id = UUID(user_id_str)
    return await generate_nl_sql_and_save(data, db, user_id)
