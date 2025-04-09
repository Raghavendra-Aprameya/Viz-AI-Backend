from fastapi import APIRouter, status, Response, Depends, Request, Path
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.db import get_db
from app.schemas import ProjectRequest,DBConnectionResponse,DBConnectionRequest, ConnectionRequest, ProjectsResponse, DBConnectionListResponse
from app.services.project import create_project, get_projects, list_all_roles_project, create_dashboard, list_all_permissions, create_role,list_users_all_dashboard, delete_dashboard
from app.utils.token_parser import get_current_user
from app.utils.access import check_create_role_access
from app.services.db_connection import create_database_connection, get_connections
from app.services.userService import create_user_project, list_all_users_project, add_user_to_dashboard
from app.schemas import CreateUserProjectRequest, CreateUserProjectResponse, ListAllUsersProjectResponse, ListAllRolesProjectResponse, CreateDashboardRequest, CreateDashboardResponse, ListAllPermissionsResponse, CreateRoleRequest, CreateRoleResponse, AddUserDashboardRequest, AddUserDashboardResponse, ListAllUsersDashboardResponse, DeleteDashboardResponse, CreateProjectResponse


backend_router = APIRouter(prefix="/api/v1/backend", tags=["backend"])

@backend_router.post("/create-project", status_code=status.HTTP_201_CREATED)
async def create_project_route(
    project: ProjectRequest, 
    request: Request, 
    response: Response, 
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
  

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

@backend_router.post("/projects/{project_id}/dashboard", status_code=status.HTTP_201_CREATED, response_model=CreateDashboardResponse)
async def dashboard(
    project_id: UUID = Path(..., description="Project ID to create dashboard for"),
    data: CreateDashboardRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await create_dashboard(data, db, token_payload, project_id)

@backend_router.get("/permissions",status_code=status.HTTP_200_OK,response_model=ListAllPermissionsResponse)
async def list_permissions(
    db: Session = Depends(get_db),
    
):
    return await list_all_permissions(db)

@backend_router.post("/projects/{project_id}/roles", status_code=status.HTTP_201_CREATED, response_model=CreateRoleResponse)
async def create_roles(
    project_id: UUID = Path(..., description="Project ID to create role for"),
    data: CreateRoleRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
    
):
    return await create_role(data, db, token_payload, project_id)

@backend_router.post("/projects/{project_id}/dashboard/user", status_code=status.HTTP_201_CREATED, response_model=AddUserDashboardResponse)
async def add_user_dashboard(
    project_id: UUID = Path(..., description="Project ID to add user to"),
    data: AddUserDashboardRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await add_user_to_dashboard(project_id, data, db, token_payload)

@backend_router.get("/projects/{project_id}/users/dashboard", status_code=status.HTTP_200_OK, response_model=ListAllUsersDashboardResponse)
async def list_all_users_dashboard(
    project_id: UUID = Path(..., description="Project ID to list all users for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await list_users_all_dashboard(project_id, db, token_payload)

@backend_router.delete("/projects/{project_id}/dashboard/{dashboard_id}", status_code=status.HTTP_200_OK)
async def delete_dashboards(
    project_id: UUID = Path(..., description="Project ID to delete user dashboard for"),
    dashboard_id: UUID = Path(..., description="Dashboard ID to delete user dashboard for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await delete_dashboard(project_id,dashboard_id, db, token_payload)