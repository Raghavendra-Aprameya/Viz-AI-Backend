"""
This module defines all backend-related routes for managing projects, users, dashboards, roles, permissions,
database connections, and super user operations.

Routes are prefixed with `/api/v1/backend`.

Each route uses dependency injection to obtain the database session (`db`)
and the authenticated user information from a token (`token_payload`).
"""


from fastapi import APIRouter, status, Response, Depends, Request, Path, HTTPException, Body
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select
from uuid import UUID

from app.core.db import get_db
from app.utils.token_parser import get_current_user
from app.schemas import (
    ProjectRequest, DBConnectionResponse, DBConnectionRequest, UpdateDashboardRequest,
    UpdateRoleRequest, UpdateDBConnectionRequest, CreateUserProjectRequest,
    CreateUserProjectResponse, ListAllUsersProjectResponse, ListAllRolesProjectResponse,
    CreateDashboardRequest, CreateDashboardResponse, ListAllPermissionsResponse,
    CreateRoleRequest, CreateRoleResponse, AddUserDashboardRequest, AddUserDashboardResponse,
    UpdateProjectRequest, UpdateUserRequest, CreateSuperUserRequest , BlackListTableNameRequest,
    ReadDataRequest,RequestAccess,SaveChartRequest,UpdateRequestAccess,SaveChartToDashboardRequest,
    UpdateProjectRequest, UpdateUserRequest, CreateSuperUserRequest,QueryRequest,Nl2SQLChatRequest,
    UpdateFavoriteChartRequest

)

from app.services.project import (
    create_project, get_projects, list_all_roles_project, create_dashboard,
    list_all_permissions, create_role, list_users_all_dashboard, delete_dashboard, read_data_service,
    update_project, delete_project, update_dashboard, update_role, delete_role,
    get_project_owner_service, get_dashboard_owner_service, blacklist_service,update_blacklist_service,
    read_data_service
)

from app.services.db_connection import (
    create_database_connection, get_connections,
    update_db_connection, delete_db_connection
)

from app.services.userService import (
    create_user_project, list_all_users_project, add_user_to_dashboard, get_user_details,
    update_user, delete_user, create_super_user_service, get_super_user_service,
    get_users_dashboard_service, get_favorites_service
)


from app.utils.tasks import generate_charts_asynchronously
from app.services.chart import (generate_charts_service,request_access_service,
update_request_access_service,get_access_requests_service,get_charts_service,save_chart_service
,save_chart_to_dashboard_service,get_charts_for_dashboard_service,delete_chart_from_dashboard_service,
update_favorite_chart_service,get_favorite_charts_service)

from app.services.generate_queries import (
    generate_and_store_charts,execute_external_query
)
from app.services.nl2sql import (
    generate_nl_sql_and_save
)




backend_router = APIRouter(prefix="/api/v1/backend", tags=["backend"])

@backend_router.post("/create-project", status_code=status.HTTP_201_CREATED)

async def create_project_route(
    project: ProjectRequest, 
    
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
  

):
    """
Create a new project.
Args:
    project (ProjectRequest): The project data.
    db (Session): The database session.
    token_payload (dict): The token payload.
Returns:
    dict: The created project.
"""
    return await create_project(project,  db, token_payload)

@backend_router.post("/database/{project_id}", response_model=DBConnectionResponse)
async def add_database_connection(
    project_id: UUID,
    data: DBConnectionRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Create a new database connection.
    Args:
        project_id (UUID): The project ID.
        data (DBConnectionRequest): The database connection data.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The created database connection.
    """
    return await create_database_connection(project_id, token_payload, data, db)


@backend_router.get("/connections/{project_id}", status_code=status.HTTP_200_OK, response_model=dict)
async def get_connections_route(
    project_id: UUID = Path(..., description="Project ID to get connections for"),
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Get all connections for a project.
    Args:
        project_id (UUID): The project ID.
        request (Request): The request object.
        response (Response): The response object.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The connections for the project.
    """
    return await get_connections(project_id, request, response, db, token_payload)

@backend_router.get("/projects", status_code=status.HTTP_200_OK)
async def get_projects_route(
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Get all projects.
    Args:
        request (Request): The request object.
        response (Response): The response object.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The projects.
    """
    return await get_projects(request, response, db, token_payload)


@backend_router.post("/projects/{project_id}/users", status_code=status.HTTP_201_CREATED, response_model=CreateUserProjectResponse)
async def add_user_project(
    project_id: UUID = Path(..., description="Project ID to add user to"),
    data: CreateUserProjectRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Add a user to a project.
    Args:
        project_id (UUID): The project ID.
        data (CreateUserProjectRequest): The user data.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The created user.
    """
    return await create_user_project(data, db, token_payload, project_id)

@backend_router.get("/projects/{project_id}/users", status_code=status.HTTP_200_OK, response_model=ListAllUsersProjectResponse)
async def list_all_users(
    project_id: UUID = Path(..., description="Project ID to list all users for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    List all users for a project.
    Args:
        project_id (UUID): The project ID.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The users for the project.
    """
    return await list_all_users_project(project_id, db, token_payload)

@backend_router.get("/projects/{project_id}/roles", status_code=status.HTTP_200_OK, response_model=ListAllRolesProjectResponse)
async def list_all_roles(
    project_id: UUID = Path(..., description="Project ID to list all roles for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    List all roles for a project.
    Args:
        project_id (UUID): The project ID.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The roles for the project.
    """
    return await list_all_roles_project(project_id, db, token_payload)

@backend_router.post("/projects/{project_id}/dashboard", status_code=status.HTTP_201_CREATED, response_model=CreateDashboardResponse)
async def dashboard(
    project_id: UUID = Path(..., description="Project ID to create dashboard for"),
    data: CreateDashboardRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Create a new dashboard.
    Args:
        project_id (UUID): The project ID.
        data (CreateDashboardRequest): The dashboard data.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The created dashboard.
    """
    return await create_dashboard(data, db, token_payload, project_id)

@backend_router.get("/permissions",status_code=status.HTTP_200_OK,response_model=ListAllPermissionsResponse)
async def list_permissions(
    db: Session = Depends(get_db),
    
):
    """
    List all permissions.
    Args:
        db (Session): The database session.
    Returns:
        dict: The permissions.
    """
    return await list_all_permissions(db)


@backend_router.post("/projects/{project_id}/roles", status_code=status.HTTP_201_CREATED, response_model=CreateRoleResponse)
async def create_roles(
    project_id: UUID = Path(..., description="Project ID to create role for"),
    data: CreateRoleRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
    
):
    """
    Create a new role.
    Args:
        project_id (UUID): The project ID.
        data (CreateRoleRequest): The role data.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The created role.
    """
    return await create_role(data, db, token_payload, project_id)

@backend_router.post("/projects/{project_id}/dashboard/user", status_code=status.HTTP_201_CREATED, response_model=AddUserDashboardResponse)
async def add_user_dashboard(
    project_id: UUID = Path(..., description="Project ID to add user to"),
    data: AddUserDashboardRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):

    """
    Add a user to a dashboard.
    Args:
        project_id (UUID): The project ID.
        data (AddUserDashboardRequest): The user data.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The created user. 
    """
    return await add_user_to_dashboard(project_id, data, db, token_payload)


@backend_router.get("/projects/{project_id}/users/dashboard", status_code=status.HTTP_200_OK)
async def list_all_users_dashboard(
    project_id: UUID = Path(..., description="Project ID to list all users for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    List all users for a dashboard.
    Args:
        project_id (UUID): The project ID.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The users for the dashboard.
    """
    return await list_users_all_dashboard(project_id, db, token_payload)

@backend_router.delete("/projects/{project_id}/dashboard/{dashboard_id}", status_code=status.HTTP_200_OK)
async def delete_dashboards(
    project_id: UUID = Path(..., description="Project ID to delete user dashboard for"),
    dashboard_id: UUID = Path(..., description="Dashboard ID to delete user dashboard for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Delete a user from a dashboard.
    Args:
        project_id (UUID): The project ID.
        dashboard_id (UUID): The dashboard ID.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The deleted user.
    """
    return await delete_dashboard(project_id,dashboard_id, db, token_payload)

@backend_router.get("/user_profile", status_code=status.HTTP_200_OK)
async def get_current_user_details(
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Get the current user's details.
    Args:
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The current user's details.
    """ 
    return await get_user_details(db, token_payload)

@backend_router.patch("/projects/{project_id}",status_code=status.HTTP_200_OK)
async def update(
    project_id: UUID = Path(..., description="Project ID to update"),
    data: UpdateProjectRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Update a project.
    Args:
        project_id (UUID): The project ID.
        data (UpdateProjectRequest): The project data.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The updated project.
    """
    return await update_project(project_id, data, db, token_payload)

@backend_router.delete("/projects/{project_id}",status_code=status.HTTP_200_OK)
async def delete(
    project_id: UUID = Path(..., description="Project ID to delete"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Delete a project.
    Args:
        project_id (UUID): The project ID.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The deleted project.
    """
    return await delete_project(project_id, db, token_payload)

@backend_router.patch("/projects/{project_id}/dashboard/{dashboard_id}",status_code=status.HTTP_200_OK)
async def update(
    project_id: UUID = Path(..., description="Project ID to update"),
    dashboard_id: UUID = Path(..., description="Dashboard ID to update"),
    data: UpdateDashboardRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)

):
    """
    Update a dashboard.
    Args:
        project_id (UUID): The project ID.
        dashboard_id (UUID): The dashboard ID.
        data (UpdateDashboardRequest): The dashboard data.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The updated dashboard.
    """
    return await update_dashboard(project_id,dashboard_id, data, db, token_payload)


@backend_router.patch("/projects/{project_id}/role/{role_id}",status_code=status.HTTP_200_OK)
async def update(
    project_id: UUID = Path(..., description="Project ID to update"),
    role_id: UUID = Path(..., description="Role ID to update"),
    data: UpdateRoleRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Update a role.
    Args:
        project_id (UUID): The project ID.
        role_id (UUID): The role ID.
        data (UpdateRoleRequest): The role data.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The updated role.
    """
    return await update_role(project_id,role_id, data, db, token_payload)

@backend_router.delete("/projects/{project_id}/role/{role_id}",status_code=status.HTTP_200_OK)
async def delete(
    project_id: UUID = Path(..., description="Project ID to delete"),
    role_id: UUID = Path(..., description="Role ID to delete"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Delete a role.
    Args:
        project_id (UUID): The project ID.
        role_id (UUID): The role ID.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The deleted role.
    """
    return await delete_role(project_id,role_id, db, token_payload)

@backend_router.patch("/projects/{project_id}/users/{user_id}",status_code=status.HTTP_200_OK)
async def update(
    project_id: UUID = Path(..., description="Project ID to update user for"),
    user_id: UUID = Path(..., description="User ID to update"),
    data: UpdateUserRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Update a user.
    Args:
        project_id (UUID): The project ID.
        user_id (UUID): The user ID.
        data (UpdateUserRequest): The user data.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The updated user.
    """
    return await update_user(project_id, user_id, data, db, token_payload)

@backend_router.delete("/projects/{project_id}/users/{user_id}",status_code=status.HTTP_200_OK)
async def delete(
    project_id: UUID = Path(..., description="Project ID to delete user for"),
    user_id: UUID = Path(..., description="User ID to delete"),
    token_payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db)

):
    """
    Delete a user.
    Args:
        project_id (UUID): The project ID.
        user_id (UUID): The user ID.
        db (Session): The database session.
    Returns:
        dict: The deleted user.
    """
    return await delete_user(project_id,user_id,token_payload, db)

@backend_router.patch("/connections/{connection_id}",status_code=status.HTTP_200_OK)
async def update(
    connection_id: UUID = Path(..., description="Connection ID to update"),
    data: UpdateDBConnectionRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Update a database connection.
    Args:
        connection_id (UUID): The connection ID.
        data (UpdateDBConnectionRequest): The connection data.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The updated connection.
    """
    return await update_db_connection(connection_id, data, db, token_payload)

@backend_router.delete("/connections/{connection_id}",status_code=status.HTTP_200_OK)
async def delete(
    connection_id: UUID = Path(..., description="Connection ID to delete"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)

):
    """
    Delete a database connection.
    Args:
        connection_id (UUID): The connection ID.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The deleted connection.
    """
    return await delete_db_connection(connection_id, db,token_payload)

@backend_router.post("/super-user",status_code=status.HTTP_201_CREATED)
async def create_super_user(
    data: CreateSuperUserRequest ,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Create a new super user.
    Args:
        data (CreateSuperUserRequest): The super user data.
        db (Session): The database session.
    Returns:
        dict: The created super user.
    """
    return await create_super_user_service(data, db,token_payload)

@backend_router.get("/super-user",status_code=status.HTTP_200_OK)
async def get_super_user(
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)     
):
    """
    Get the super user.
    Args:
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The super user.
    """
    return await get_super_user_service(db,token_payload)

@backend_router.get("/dashboard/{dashboard_id}/users",status_code=status.HTTP_200_OK)
async def get_users_dashboard(
    dashboard_id: UUID = Path(..., description="Dashboard ID to get users for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Get the users for a dashboard.
    Args:
        dashboard_id (UUID): The dashboard ID.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The users for the dashboard.
    """
    return await get_users_dashboard_service(dashboard_id, db, token_payload) 

@backend_router.get("/projects/{project_id}/owners",status_code=status.HTTP_200_OK)
async def get_project_owner(
    project_id: UUID = Path(..., description="Project ID to get owner for"),
    db: Session = Depends(get_db),
):
    """
    Get the owner for a project.
    Args:
        project_id (UUID): The project ID.
        db (Session): The database session.
    Returns:
        dict: The owner for the project.
    """
    return await get_project_owner_service(project_id, db)

@backend_router.get("/dashboards/{dashboard_id}/owners",status_code=status.HTTP_200_OK)
async def get_dashboard_owner(
    dashboard_id: UUID = Path(..., description="Dashboard ID to get owner for"),
    db: Session = Depends(get_db),  
):
    """
    Get the owner for a dashboard.
    Args:
        dashboard_id (UUID): The dashboard ID.
        db (Session): The database session.
    Returns:
        dict: The owner for the dashboard.
    """
    return await get_dashboard_owner_service(dashboard_id, db)

@backend_router.get("/favorites",status_code=status.HTTP_200_OK)
async def get_favorites(
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user) 
):
    """
    Get the favorites for a user.
    Args:
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The favorites for the user.
    """
    return await get_favorites_service(db, token_payload)


@backend_router.post("/projects/{project_id}/blacklist", status_code=status.HTTP_200_OK)
async def blacklist(
    project_id: UUID = Path(..., description="Project ID to blacklist tables for"),
    data: BlackListTableNameRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Blacklist tables for a project.
    Args:
        project_id (UUID): The project ID.
        data (BlackListTableNameRequest): The table names to blacklist.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The blacklisted tables response.
    """
    return await blacklist_service(project_id, data, db, token_payload)

@backend_router.patch("/projects/{project_id}/blacklist", status_code=status.HTTP_200_OK)
async def update_blacklist(
    project_id: UUID = Path(..., description="Project ID to update blacklist tables for"),
    data: BlackListTableNameRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)     \
):
    """
    Update blacklist tables for a project.
    Args:
        project_id (UUID): The project ID.
        data (BlackListTableNameRequest): The table names to update blacklist.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The updated blacklisted tables response.
    """
    return await update_blacklist_service(project_id, data, db, token_payload)

@backend_router.patch("/grant-access", status_code=status.HTTP_200_OK)
async def grant_access(
    data: ReadDataRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Grant access to a project.
    Args:
        data (ReadDataRequest): The grant access data.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The grant access response.
    """
    return await read_data_service(data, db, token_payload)

# @backend_router.post("/generate-charts/{project_id}/{datasource_connection_id}")
# async def generate_charts(
#     request: QueryRequest,
#     project_id: UUID = Path(..., description="Project ID to generate charts for"),
#     datasource_connection_id: UUID = Path(..., description="Datasource connection ID to generate charts for"),
#     db: Session = Depends(get_db),
#     token_payload: dict = Depends(get_current_user)
# ):
#     """
#     API endpoint to generate charts for a specific project and datasource connection.
    
#     Args:
#         request (QueryRequest): Query parameters for chart generation
#         project_id (UUID): ID of the project
#         datasource_connection_id (UUID): ID of the datasource connection
#         db (Session): Database session
#         token_payload (dict): User authentication token payload
        
#     Returns:
#         dict: Generated charts data and status information
#     """
#     return await generate_charts_service(
#         request,
#         project_id,
#         datasource_connection_id,
#         db,
#         token_payload
#     )
# @backend_router.get("/refresh-charts", status_code=status.HTTP_200_OK)
# async def refresh_charts(
#     db: Session = Depends(get_db),
#     token_payload: dict = Depends(get_current_user),
#     datasource_connection_id: UUID = Query(..., description="ID of the datasource connection"),
#     project_id: UUID = Query(..., description="ID of the project")
# ):
#     """
#     Endpoint to refresh charts using pre-generated charts from Redis.
    
#     This endpoint:
#     1. Retrieves pre-generated charts from Redis
#     2. Sets them as the current charts
#     3. Triggers asynchronous generation of the next batch
    
#     Args:
#         db (Session): The database session
#         token_payload (dict): The token payload
#         datasource_connection_id (UUID): ID of the datasource connection
#         project_id (UUID): ID of the project
        
#     Returns:
#         dict: Refreshed charts data and status information
#     """
#     return await refresh_service(
#         db=db,
#         datasource_connection_id=datasource_connection_id,
#         project_id=project_id,
#         token_payload=token_payload
#     )

@backend_router.post("/projects/{project_id}/request-access", status_code=status.HTTP_200_OK)
async def request_access(
    project_id: UUID = Path(..., description="Project ID to request access for"),
    data:RequestAccess = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await request_access_service(project_id, data, db, token_payload)

@backend_router.post("/generate_charts/{project_id}/{datasource_connection_id}")
async def generate_charts(
    project_id: UUID,
    datasource_connection_id: UUID,
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
        charts = await generate_and_store_charts(db,datasource_connection_id,project_id, request,token_payload)
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

@backend_router.post("/excecute-query/{query_id}/{datasource_connection_id}/")
def execute_query(
    query_id: UUID,
    datasource_connection_id:UUID,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    try:
        query_result =  execute_external_query(query_id,db, datasource_connection_id,token_payload)
        return query_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


@backend_router.patch("/projects/{project_id}/request-access/{request_id}", status_code=status.HTTP_200_OK)
async def update_request_access(
    project_id: UUID = Path(..., description="Project ID to update request access for"),
    request_id: UUID = Path(..., description="Request ID to update"),
    data:UpdateRequestAccess = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await update_request_access_service(project_id,request_id, data, db, token_payload)

@backend_router.get("/projects/{project_id}/request-access", status_code=status.HTTP_200_OK)
async def get_request_access(
    project_id: UUID = Path(..., description="Project ID to get request access for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)     
):
    return await get_access_requests_service(project_id, db, token_payload)

@backend_router.get("/charts", status_code=status.HTTP_200_OK)
async def get_charts(
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await get_charts_service(db, token_payload)

@backend_router.post("/projects/{project_id}/save-chart", status_code=status.HTTP_200_OK)
async def save_chart(
    project_id: UUID = Path(..., description="Project ID to save chart for"),
    data: SaveChartRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user) 
):
    return await save_chart_service(project_id, data, db, token_payload)

@backend_router.post("/charts/save-to-dashboard", status_code=status.HTTP_200_OK)
async def save_chart_to_dashboard(
    data: SaveChartToDashboardRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await save_chart_to_dashboard_service(data, db, token_payload)

@backend_router.get("/dashboards/{dashboard_id}/charts", status_code=status.HTTP_200_OK)
async def get_charts_for_dashboard(
    dashboard_id: UUID = Path(..., description="Dashboard ID to get charts for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await get_charts_for_dashboard_service(dashboard_id, db, token_payload)

@backend_router.delete("/dashboards/{dashboard_id}/charts/{chart_id}", status_code=status.HTTP_200_OK)
async def delete_chart_from_dashboard(
    dashboard_id: UUID = Path(..., description="Dashboard ID to delete chart from"),
    chart_id: UUID = Path(..., description="Chart ID to delete"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user) 
):
    return await delete_chart_from_dashboard_service(dashboard_id, chart_id, db, token_payload)

@backend_router.patch("/charts/favorite", status_code=status.HTTP_200_OK)
async def update_favorite_chart(
    data: UpdateFavoriteChartRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await update_favorite_chart_service(data, db, token_payload)
@backend_router.get("/charts/favorite", status_code=status.HTTP_200_OK)
async def get_favorite_charts(
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return await get_favorite_charts_service(db, token_payload)

