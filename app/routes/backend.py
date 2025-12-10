"""
Backend routes for managing projects, dashboards, users, roles, permissions,
and database connections. All routes are prefixed with `/api/v1/backend` and
use dependency injection for DB session and user authentication.
"""

from uuid import UUID
from typing import Optional
import traceback
from fastapi import (
    APIRouter,
    status,
    Response,
    Depends,
    Request,
    Path,
    HTTPException,
    Body,
    Query,
    BackgroundTasks,
    WebSocket,
    WebSocketDisconnect
)
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import get_db
from app.utils.token_parser import get_current_user

# Schema imports
from app.schemas import (
    ProjectRequest,
    UpdateProjectRequest,
    UpdateProjectKpiInfoRequest,
    UpdateUserRequest,
    CreateSuperUserRequest,
    DBConnectionRequest,
    UpdateDBConnectionRequest,
    DBConnectionResponse,
    CreateUserProjectRequest,
    CreateUserProjectResponse,
    ListAllUsersProjectResponse,
    ListAllRolesProjectResponse,
    CreateDashboardRequest,
    CreateDashboardResponse,
    UpdateDashboardRequest,
    AddUserDashboardRequest,
    AddUserDashboardResponse,
    CreateRoleRequest,
    CreateRoleResponse,
    UpdateRoleRequest,
    ListAllPermissionsResponse,
    BlackListTableNameRequest,
    ReadDataRequest,
    RequestAccess,
    SaveChartRequest,
    UpdateRequestAccess,
    SaveChartToDashboardRequest,
    QueryRequest,
    Nl2SQLChatRequest,
    UpdateFavoriteChartRequest,
    TrinoQueryRequest,
    TrinoQueryResponse,
    QueryExecutionRequest,
    DashboardStatsResponse,
    PinnedChartsCountResponse,
    BusinessInsightsRequest,
    BusinessInsightsResponse,
    ProjectInsightsResponse,
    LatestBusinessInsightResponse,
    ConnectionStatsResponse,
    ConnectionCheckResponse,
)

# Service imports
from app.services.project import (
    create_project,
    get_projects,
    list_all_roles_project,
    create_dashboard,
    list_all_permissions,
    create_role,
    list_users_all_dashboard,
    delete_dashboard,
    update_project,
    update_project_kpi_info,
    delete_project,
    update_dashboard,
    update_role,
    delete_role,
    get_project_owner_service,
    get_dashboard_owner_service,
    blacklist_service,
    update_blacklist_service,
    read_data_service,
)

from app.services.db_connection import (
    create_database_connection,
    get_connections,
    update_db_connection,
    delete_db_connection,
    get_connection_stats,
    check_and_update_connections,
    progress_queues
)

from app.services.userService import (
    create_user_project,
    list_all_users_project,
    add_user_to_dashboard,
    get_user_details,
    update_user,
    delete_user,
    create_super_user_service,
    get_super_user_service,
    get_users_dashboard_service,
    get_favorites_service,
    get_dashboard_stats_service,
)

from app.services.chart import (
    request_access_service,
    update_request_access_service,
    get_access_requests_service,
    get_charts_service,
    save_chart_service,
    save_chart_to_dashboard_service,
    get_charts_for_dashboard_service,
    get_user_dashboard_charts_service,
    delete_chart_from_dashboard_service,
    update_favorite_chart_service,
    get_favorite_charts_service,
    get_user_favorite_charts_service,
    get_pinned_charts_count_service,
    filter_charts_service,
)

from app.services.business_insights import generate_business_insights_service
from app.services.project_insights import (
    generate_project_insights_service,
    get_latest_business_insight_service,
)

from app.services.generate_queries import (
    generate_and_store_charts,
    execute_external_query,
)

from app.services.nl2sql import generate_nl_sql

from app.services.multiple_db_generate_queries import generate_trino_queries_service




backend_router = APIRouter(prefix="/api/v1/backend", tags=["backend"])


@backend_router.post("/create-project", status_code=status.HTTP_201_CREATED)
async def create_project_route(
    project: ProjectRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Create a new project.
    Args:s
        project (ProjectRequest): The project data.
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The created project.
    """
    return await create_project(project, db, token_payload)


@backend_router.post("/database/{project_id}", response_model=DBConnectionResponse)
async def add_database_connection(
    project_id: UUID,
    data: DBConnectionRequest,
    background_tasks:BackgroundTasks,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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
    return await create_database_connection(project_id, token_payload, data, db,background_tasks)

@backend_router.websocket("/ws/progress/{task_id}")
async def ws_progress(ws: WebSocket, task_id: str):
    await ws.accept()
    queue = progress_queues.get(task_id)
    if not queue:
        await ws.send_json({"type": "error", "message": "Invalid taskId"})
        await ws.close()
        return
    try:
        while True:
            msg = await queue.get()
            if msg is None:
                break  # worker finished
            await ws.send_json(msg)
    except WebSocketDisconnect:
        print(f"Client disconnected from task {task_id}")
    finally:
        try:
            await ws.close()
        except:
            pass


@backend_router.get(
    "/connections/{project_id}", status_code=status.HTTP_200_OK, response_model=dict
)
async def get_connections_route(
    project_id: UUID = Path(..., description="Project ID to get connections for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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
    return await get_connections(project_id, db, token_payload)


@backend_router.get(
    "/connections/{project_id}/stats",
    status_code=status.HTTP_200_OK,
    response_model=ConnectionStatsResponse,
)
async def get_connection_stats_route(
    project_id: UUID = Path(..., description="Project ID to get connection stats for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Get database connection statistics for a project.
    
    This endpoint provides statistics about database connections including:
    - Total number of connections
    - Number of active connections (status=True)
    - Number of inactive connections (status=False)
    
    Args:
        project_id (UUID): The project ID.
        db (Session): The database session.
        token_payload (dict): The token payload.
        
    Returns:
        ConnectionStatsResponse: Statistics about database connections.
    """
    return await get_connection_stats(project_id, db, token_payload)


@backend_router.post(
    "/connections/{project_id}/check",
    status_code=status.HTTP_200_OK,
    response_model=ConnectionCheckResponse,
)
async def check_connections_route(
    project_id: UUID = Path(..., description="Project ID to check connections for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Check all database connections for a project and update their status.
    
    This endpoint tests each database connection by attempting to connect to it.
    For each connection, it:
    - Tests if the connection can be established
    - Updates the 'status' field (True if successful, False if failed)
    - Updates the 'last_checked' timestamp with the current time
    - Returns detailed results for each connection including error messages if any
    
    Args:
        project_id (UUID): The project ID.
        db (Session): The database session.
        token_payload (dict): The token payload.
        
    Returns:
        ConnectionCheckResponse: Results of connection checks with updated status.
    """
    return await check_and_update_connections(project_id, db, token_payload)


@backend_router.get("/projects", status_code=status.HTTP_200_OK)
async def get_projects_route(
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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
    return await get_projects(db, token_payload)


@backend_router.post(
    "/projects/{project_id}/users",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateUserProjectResponse,
)
async def add_user_project(
    project_id: UUID = Path(..., description="Project ID to add user to"),
    data: CreateUserProjectRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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


@backend_router.get(
    "/projects/{project_id}/users",
    status_code=status.HTTP_200_OK,
    response_model=ListAllUsersProjectResponse,
)
async def list_all_users(
    project_id: UUID = Path(..., description="Project ID to list all users for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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


@backend_router.get(
    "/projects/{project_id}/roles",
    status_code=status.HTTP_200_OK,
    response_model=ListAllRolesProjectResponse,
)
async def list_all_roles(
    project_id: UUID = Path(..., description="Project ID to list all roles for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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


@backend_router.post(
    "/projects/{project_id}/dashboard",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateDashboardResponse,
)
async def dashboard(
    project_id: UUID = Path(..., description="Project ID to create dashboard for"),
    data: CreateDashboardRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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


@backend_router.get(
    "/permissions",
    status_code=status.HTTP_200_OK,
    response_model=ListAllPermissionsResponse,
)
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


@backend_router.post(
    "/projects/{project_id}/roles",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateRoleResponse,
)
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


@backend_router.post(
    "/projects/{project_id}/dashboard/user",
    status_code=status.HTTP_201_CREATED,
    response_model=AddUserDashboardResponse,
)
async def add_user_dashboard(
    project_id: UUID = Path(..., description="Project ID to add user to"),
    data: AddUserDashboardRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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


@backend_router.get(
    "/projects/{project_id}/users/dashboard", status_code=status.HTTP_200_OK
)
async def list_all_users_dashboard(
    project_id: UUID = Path(..., description="Project ID to list all users for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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


@backend_router.delete(
    "/projects/{project_id}/dashboard/{dashboard_id}", status_code=status.HTTP_200_OK
)
async def delete_dashboards(
    project_id: UUID = Path(..., description="Project ID to delete user dashboard for"),
    dashboard_id: UUID = Path(
        ..., description="Dashboard ID to delete user dashboard for"
    ),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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
    return await delete_dashboard(project_id, dashboard_id, db, token_payload)


@backend_router.get("/user_profile", status_code=status.HTTP_200_OK)
async def get_current_user_details(
    db: Session = Depends(get_db), token_payload: dict = Depends(get_current_user)
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


@backend_router.patch("/projects/{project_id}", status_code=status.HTTP_200_OK)
async def update(
    project_id: UUID = Path(..., description="Project ID to update"),
    data: UpdateProjectRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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


@backend_router.patch(
    "/projects/{project_id}/kpi-info",
    status_code=status.HTTP_200_OK,
)
async def update_project_kpi_info_route(
    project_id: UUID = Path(..., description="Project ID to update KPI info for"),
    data: UpdateProjectKpiInfoRequest = Body(
        ..., description="Payload containing KPI information for the project"
    ),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Update the KPI information for a project.
    """
    return await update_project_kpi_info(project_id, data, db, token_payload)


@backend_router.delete("/projects/{project_id}", status_code=status.HTTP_200_OK)
async def delete(
    project_id: UUID = Path(..., description="Project ID to delete"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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


@backend_router.patch(
    "/projects/{project_id}/dashboard/{dashboard_id}", status_code=status.HTTP_200_OK
)
async def update_dashboard_route(
    project_id: UUID = Path(..., description="Project ID to update"),
    dashboard_id: UUID = Path(..., description="Dashboard ID to update"),
    data: UpdateDashboardRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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
    return await update_dashboard(project_id, dashboard_id, data, db, token_payload)


@backend_router.patch(
    "/projects/{project_id}/role/{role_id}", status_code=status.HTTP_200_OK
)
async def update_role_route(
    project_id: UUID = Path(..., description="Project ID to update"),
    role_id: UUID = Path(..., description="Role ID to update"),
    data: UpdateRoleRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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
    return await update_role(project_id, role_id, data, db, token_payload)


@backend_router.delete(
    "/projects/{project_id}/role/{role_id}", status_code=status.HTTP_200_OK
)
async def delete_role_route(
    project_id: UUID = Path(..., description="Project ID to delete"),
    role_id: UUID = Path(..., description="Role ID to delete"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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
    return await delete_role(project_id, role_id, db, token_payload)


@backend_router.patch(
    "/projects/{project_id}/users/{user_id}", status_code=status.HTTP_200_OK
)
async def update_user_route(
    project_id: UUID = Path(..., description="Project ID to update user for"),
    user_id: UUID = Path(..., description="User ID to update"),
    data: UpdateUserRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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


@backend_router.delete(
    "/projects/{project_id}/users/{user_id}", status_code=status.HTTP_200_OK
)
async def delete_user_route(
    project_id: UUID = Path(..., description="Project ID to delete user for"),
    user_id: UUID = Path(..., description="User ID to delete"),
    token_payload: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
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
    return await delete_user(project_id, user_id, token_payload, db)


@backend_router.patch("/connections/{connection_id}", status_code=status.HTTP_200_OK)
async def update_connection_route(
    connection_id: UUID = Path(..., description="Connection ID to update"),
    data: UpdateDBConnectionRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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
    return await update_db_connection(
        connection_id=connection_id,
        data=data,
        db=db,
        token_payload=token_payload,
    )


@backend_router.delete("/connections/{connection_id}", status_code=status.HTTP_200_OK)
async def delete_connection_route(
    connection_id: UUID = Path(..., description="Connection ID to delete"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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
    return await delete_db_connection(connection_id, db, token_payload)


@backend_router.post("/super-user", status_code=status.HTTP_201_CREATED)
async def create_super_user(
    data: CreateSuperUserRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Create a new super user.
    Args:
        data (CreateSuperUserRequest): The super user data.
        db (Session): The database session.
    Returns:
        dict: The created super user.
    """
    return await create_super_user_service(data, db, token_payload)


@backend_router.get("/super-user", status_code=status.HTTP_200_OK)
async def get_super_user(
    db: Session = Depends(get_db), token_payload: dict = Depends(get_current_user)
):
    """
    Get the super user.
    Args:
        db (Session): The database session.
        token_payload (dict): The token payload.
    Returns:
        dict: The super user.
    """
    return await get_super_user_service(db, token_payload)


@backend_router.get("/dashboard/{dashboard_id}/users", status_code=status.HTTP_200_OK)
async def get_users_dashboard(
    dashboard_id: UUID = Path(..., description="Dashboard ID to get users for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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


@backend_router.get("/projects/{project_id}/owners", status_code=status.HTTP_200_OK)
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


@backend_router.get("/dashboards/{dashboard_id}/owners", status_code=status.HTTP_200_OK)
async def get_dashboard_owner(
    dashboard_id: UUID = Path(..., description="Dashboard ID to get owner for"),
    db: Session = Depends(get_db),
):
    """
    Get the owner for a dashboard.
    Args:
        dashboard_id (UUID): The dashboard ID.
        db (Session): The database session.
    Returns:`̀
        dict: The owner for the dashboard.
    """
    return await get_dashboard_owner_service(dashboard_id, db)


@backend_router.get("/favorites", status_code=status.HTTP_200_OK)
async def get_favorites(
    db: Session = Depends(get_db), token_payload: dict = Depends(get_current_user)
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
    token_payload: dict = Depends(get_current_user),
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


@backend_router.patch(
    "/projects/{project_id}/blacklist", status_code=status.HTTP_200_OK
)
async def update_blacklist(
    project_id: UUID = Path(
        ..., description="Project ID to update blacklist tables for"
    ),
    data: BlackListTableNameRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
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
    token_payload: dict = Depends(get_current_user),
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


@backend_router.post(
    "/projects/{project_id}/request-access", status_code=status.HTTP_200_OK
)
@backend_router.post("/projects/{project_id}/request-access")
async def request_access(
    project_id: UUID = Path(..., description="Project ID to request access for"),
    data: RequestAccess = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Request access to a specific project.

    Args:
        project_id (UUID): The ID of the project to request access for.
        data (RequestAccess): Request access payload.
        db (Session): Database session.
        token_payload (dict): Authenticated user payload.

    Returns:
        dict: Response from the request access service.
    """
    return await request_access_service(project_id, data, db, token_payload)


@backend_router.post("/generate_charts/{project_id}/{datasource_connection_id}")
async def generate_charts(
    project_id: UUID,
    datasource_connection_id: UUID,
    request: QueryRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    try:
        charts = await generate_and_store_charts(
            db, datasource_connection_id, project_id, request, token_payload
        )

        return {
            "success": True,
            "generated_charts": [
                {
                    "id": str(chart.id),
                    "title": chart.title,
                    "query": chart.query,
                    "chart_type": chart.chart_type,
                    "relevance": chart.relevance,
                    "is_time_based": chart.is_time_based,
                    "report": chart.report,
                }
                for chart in charts
            ],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@backend_router.post("/nl2sql/generate/{datasource_connection_id}")
async def generate_and_save_route(
    data: Nl2SQLChatRequest = Body(...),
    db: Session = Depends(get_db),
    datasource_connection_id: UUID = Path(...),
    token_payload: dict = Depends(get_current_user),
):
    """
    Generate and store SQL queries from natural language input.

    Args:
        data (Nl2SQLChatRequest): Natural language input for query generation.
        db (Session): Database session.
        datasource_connection_id (UUID): Connection ID for the target datasource.
        token_payload (dict): Authenticated user payload.

    Returns:
        dict: Generated SQL query and related metadata.
    """
    user_id_str = token_payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user_id = UUID(user_id_str)
    return await generate_nl_sql(data, db, user_id, datasource_connection_id)


@backend_router.post("/excecute-query/{datasource_connection_id}/")
def execute_query(
    datasource_connection_id: UUID,
    db: Session = Depends(get_db),
    request: QueryExecutionRequest = Body(...),
    token_payload: dict = Depends(get_current_user),
):
    """
    Execute a raw SQL query against the specified datasource.

    Args:
        query_id (UUID): Query identifier.
        datasource_connection_id (UUID): Datasource connection ID.
        db (Session): Database session.
        request (QueryExecutionRequest): Query to execute.
        token_payload (dict): Authenticated user payload.

    Returns:
        dict: Query execution result.
    """
    try:
        return execute_external_query(
            db=db,
            datasource_connection_id=datasource_connection_id,
            query_input=request.query,
            token_payload=token_payload,
            from_date=request.from_date,
            to_date=request.to_date,
        )
    except SQLAlchemyError as e:
        # Explicitly re-raise the exception with context
        raise HTTPException(
            status_code=500, detail=f"Database execution error: {str(e)}"
        ) from e

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"ValueError: {str(e)}") from e

    except Exception as e:
        # Print the stack trace for debugging purposes
        traceback.print_exc()
        # Explicitly re-raise the unexpected exception with more context
        raise HTTPException(status_code=500, detail="Unexpected error occurred") from e


@backend_router.post(
    "/generate_multiple_db_queries/{project_id}/", response_model=TrinoQueryResponse
)
async def generate_queries_route(
    project_id: UUID,
    request: TrinoQueryRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Generate Trino SQL queries for multiple database connections.

    Args:
        project_id (UUID): Project identifier.
        request (TrinoQueryRequest): Payload including connection IDs and other context.
        db (Session): Database session.
        token_payload (dict): Authenticated user payload.

    Returns:
        TrinoQueryResponse: Generated SQL queries for each connection.
    """
    if not request.connection_ids:
        raise HTTPException(status_code=400, detail="Connection IDs are required")

    return await generate_trino_queries_service(
        db=db, project_id=project_id, token_payload=token_payload, request=request
    )


@backend_router.patch(
    "/projects/{project_id}/request-access/{request_id}", status_code=status.HTTP_200_OK
)
async def update_request_access(
    project_id: UUID = Path(..., description="Project ID to update request access for"),
    request_id: UUID = Path(..., description="Request ID to update"),
    data: UpdateRequestAccess = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Update the request access for a specific project.

    Args:
        project_id (UUID): The ID of the project.
        request_id (UUID): The ID of the request to update.
        data (UpdateRequestAccess): The data to update the request access with.
        db (Session): The database session.
        token_payload (dict): The authenticated user's token payload.

    Returns:
        dict: The updated request access data.
    """
    return await update_request_access_service(
        project_id, request_id, data, db, token_payload
    )


@backend_router.get(
    "/projects/{project_id}/request-access", status_code=status.HTTP_200_OK
)
async def get_request_access(
    project_id: UUID = Path(..., description="Project ID to get request access for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Retrieve the request access for a specific project.

    Args:
        project_id (UUID): The ID of the project to get the request access for.
        db (Session): The database session.
        token_payload (dict): The authenticated user's token payload.

    Returns:
        dict: The request access data for the specified project.
    """
    return await get_access_requests_service(project_id, db, token_payload)


# @backend_router.get("/charts", status_code=status.HTTP_200_OK)
# async def get_charts(
#     db: Session = Depends(get_db),
#     token_payload: dict = Depends(get_current_user)
# ):
#     return await get_charts_service(db, token_payload)


@backend_router.post(
    "/projects/{project_id}/save-chart", status_code=status.HTTP_200_OK
)
async def save_chart(
    project_id: UUID = Path(..., description="Project ID to save chart for"),
    data: SaveChartRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Save a chart for the specified project.

    Args:
        project_id (UUID): The ID of the project to save the chart for.
        data (SaveChartRequest): The chart data to save.
        db (Session): The database session.
        token_payload (dict): The payload of the current authenticated user.

    Returns:
        dict: The response containing the saved chart details.
    """
    return await save_chart_service(project_id, data, db, token_payload)


@backend_router.post("/charts/save-to-dashboard", status_code=status.HTTP_200_OK)
async def save_chart_to_dashboard(
    data: SaveChartToDashboardRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Save a chart to the specified dashboard.

    Args:
        data (SaveChartToDashboardRequest): The chart data and dashboard ID to save to.
        db (Session): The database session.
        token_payload (dict): The payload of the current authenticated user.

    Returns:
        dict: The response indicating the chart has been saved to the dashboard.
    """
    return await save_chart_to_dashboard_service(data, db, token_payload)


@backend_router.get("/dashboards/user/charts", status_code=status.HTTP_200_OK)
async def get_user_dashboard_charts(
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Get all charts from dashboards that the current user is a member of.
    """
    return await get_user_dashboard_charts_service(db, token_payload)


@backend_router.get("/dashboards/{dashboard_id}/charts", status_code=status.HTTP_200_OK)
async def get_charts_for_dashboard(
    dashboard_id: UUID = Path(..., description="Dashboard ID to get charts for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Get all charts for the specified dashboard.

    Args:
        dashboard_id (UUID): The ID of the dashboard to retrieve charts for.
        db (Session): The database session.
        token_payload (dict): The payload of the current authenticated user.

    Returns:
        list: A list of charts associated with the specified dashboard.
    """
    return await get_charts_for_dashboard_service(dashboard_id, db, token_payload)


@backend_router.delete(
    "/dashboards/{dashboard_id}/charts/{chart_id}", status_code=status.HTTP_200_OK
)
async def delete_chart_from_dashboard(
    dashboard_id: UUID = Path(..., description="Dashboard ID to delete chart from"),
    chart_id: UUID = Path(..., description="Chart ID to delete"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Delete a chart from the specified dashboard.

    Args:
        dashboard_id (UUID): The ID of the dashboard to delete the chart from.
        chart_id (UUID): The ID of the chart to delete.
        db (Session): The database session.
        token_payload (dict): The payload of the current authenticated user.

    Returns:
        dict: A response indicating the chart has been successfully deleted.
    """
    return await delete_chart_from_dashboard_service(
        dashboard_id, chart_id, db, token_payload
    )


@backend_router.patch("/charts/favorite", status_code=status.HTTP_200_OK)
async def update_favorite_chart(
    data: UpdateFavoriteChartRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Update the favorite status of a chart.

    Args:
        data (UpdateFavoriteChartRequest): The data to update the favorite status of a chart.
        db (Session): The database session.
        token_payload (dict): The payload of the current authenticated user.

    Returns:
        dict: The updated favorite chart details.
    """
    return await update_favorite_chart_service(data, db, token_payload)


@backend_router.get("/charts/favorite", status_code=status.HTTP_200_OK)
async def get_favorite_charts(
    db: Session = Depends(get_db), token_payload: dict = Depends(get_current_user)
):
    """
    Get all favorite charts for the authenticated user.

    Args:
        db (Session): The database session.
        token_payload (dict): The payload of the current authenticated user.

    Returns:
        list: A list of favorite charts for the authenticated user.
    """
    return await get_favorite_charts_service(db, token_payload)


@backend_router.get(
    "/users/charts/favorite", status_code=status.HTTP_200_OK
)
async def get_user_favorite_charts(
    
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """Retrieve favorite charts for the specified user."""

    return await get_user_favorite_charts_service(db, token_payload)


@backend_router.get(
    "/charts/pinned/count",
    status_code=status.HTTP_200_OK,
    response_model=PinnedChartsCountResponse,
)
async def get_pinned_charts_count(
    db: Session = Depends(get_db), token_payload: dict = Depends(get_current_user)
):
    """
    Get the count of pinned (favorite) charts for the authenticated user.

    Args:
        db (Session): The database session.
        token_payload (dict): The payload of the current authenticated user.

    Returns:
        PinnedChartsCountResponse: The count of pinned charts for the authenticated user.
    """
    return await get_pinned_charts_count_service(db, token_payload)


@backend_router.get("/charts", status_code=status.HTTP_200_OK)
async def get_charts(
    project_id: UUID = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Get all charts for the authenticated user, optionally filtered by project.

    Args:
        project_id (UUID): Optional project ID to filter charts by.
        db (Session): The database session.
        token_payload (dict): The payload of the current authenticated user.

    Returns:
        dict: A dictionary containing charts for the authenticated user.
    """
    return await get_charts_service(db, token_payload, project_id)


@backend_router.get("/charts/filter", status_code=status.HTTP_200_OK)
async def filter_charts(
    dashboard_id: UUID = None,
    database_connection_id: UUID = None,
    status: str = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Filter charts based on multiple optional query parameters.
    
    All filter parameters are optional and can be combined:
    - dashboard_id: Filter charts by specific dashboard UUID
    - database_connection_id: Filter charts by database connection UUID
    - status: Filter charts by status ("draft" or "published")
    
    Status definitions:
    - "draft": Charts not added to any dashboard
    - "published": Charts added to at least one dashboard
    - omitted/null: All charts (no status filter)
    
    Examples:
    - /charts/filter - Get all charts
    - /charts/filter?status=draft - Get only draft charts
    - /charts/filter?dashboard_id=xxx - Get charts in specific dashboard
    - /charts/filter?dashboard_id=xxx&status=published - Combined filters

    Args:
        dashboard_id (UUID): Optional UUID of the dashboard to filter by
        database_connection_id (UUID): Optional UUID of the database connection to filter by
        status (str): Optional status filter ("draft" or "published")
        db (Session): The database session
        token_payload (dict): The payload of the current authenticated user

    Returns:
        dict: Filtered charts with metadata including:
            - charts: List of filtered chart objects
            - total_count: Number of charts returned
            - filters_applied: Summary of applied filters
    """
    return await filter_charts_service(
        db=db,
        token_payload=token_payload,
        dashboard_id=dashboard_id,
        database_connection_id=database_connection_id,
        status=status,
    )


@backend_router.get(
    "/dashboard-stats", status_code=status.HTTP_200_OK, response_model=DashboardStatsResponse
)
async def get_dashboard_stats(
    db: Session = Depends(get_db), token_payload: dict = Depends(get_current_user)
):
    """
    Get dashboard statistics for the authenticated user including:
    - Total projects user is part of
    - Active dashboards user has access to
    - Total data sources across user's projects
    - Total team members across user's projects

    Args:
        db (Session): The database session.
        token_payload (dict): The payload of the current authenticated user.

    Returns:
        DashboardStatsResponse: Dashboard statistics for the authenticated user.
    """
    return await get_dashboard_stats_service(db, token_payload)


@backend_router.post(
    "/business-insights",
    status_code=status.HTTP_200_OK,
    response_model=BusinessInsightsResponse,
)
async def generate_business_insights(
    data: BusinessInsightsRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Generate AI-powered business insights from a database connection.

    This endpoint performs a comprehensive analysis:
    1. Extracts the database schema (tables, columns, data types)
    2. Uses AI (LangChain + LLM) to identify 10 key business KPIs
    3. Generates optimized SQL queries for each KPI
    4. Executes queries against the connected database
    5. Uses AI to analyze results and generate actionable insights

    The insights include:
    - Executive summary of findings
    - Detailed analysis of key metrics
    - Identified patterns and trends
    - Actionable business recommendations
    - Areas of concern requiring attention

    Args:
        data (BusinessInsightsRequest): Contains database_connection_id and optional api_key
        db (Session): The database session
        token_payload (dict): The payload of the current authenticated user

    Returns:
        BusinessInsightsResponse: Comprehensive business insights including:
            - Generated KPI queries
            - Query execution results
            - AI-generated insights and recommendations

    Example:
        POST /api/v1/backend/business-insights
        {
            "database_connection_id": "550e8400-e29b-41d4-a716-446655440000"
        }
        
    Note:
        Gemini API key must be configured in backend environment:
        GEMINI_API_KEY=your-api-key-here
    """
    return await generate_business_insights_service(
        db=db,
        token_payload=token_payload,
        database_connection_id=data.database_connection_id,
    )


@backend_router.post(
    "/projects/{project_id}/business-insights",
    status_code=status.HTTP_200_OK,
    response_model=ProjectInsightsResponse,
)
async def generate_project_business_insights(
    project_id: UUID = Path(..., description="Project ID to analyze"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Generate comprehensive AI-powered business insights for ALL databases in a project.

    This endpoint performs a complete project-wide analysis:
    1. Fetches all database connections in the project
    2. For each database:
       - Loads cached schema from db_connection.db_schema
       - Uses AI to identify 10 key business KPIs
       - Generates optimized SQL queries for each KPI
       - Executes queries against the database
       - Uses AI to analyze results and generate insights
    3. Consolidates insights across all databases
    4. Uses AI to generate unified strategic recommendations

    The response includes:
    - Individual insights for each database (full analysis per DB)
    - Consolidated project-level strategic analysis
    - Overall business health assessment (excellent/good/fair/poor)
    - Cross-database patterns and correlations
    - Top 5 strategic priorities (ranked by impact)
    - Risk assessment (critical and moderate risks)
    - Business opportunities with potential impact

    Args:
        project_id (UUID): Project ID to analyze (from URL path)
        db (Session): The database session
        token_payload (dict): The payload of the current authenticated user

    Returns:
        ProjectInsightsResponse: Comprehensive project-wide business insights including:
            - Insights from each database in the project
            - Consolidated strategic analysis across all data sources
            - Business health score
            - Strategic priorities
            - Risk assessment
            - Opportunities

    Example:
        POST /api/v1/backend/projects/2f96eace-5738-4c9f-afba-155203ee1434/business-insights
        
        # No request body required - project_id comes from URL
        # Or optionally send empty body: {}
        
    Note:
        - Gemini API key must be configured: GEMINI_API_KEY in .env
        - This can take 30-120 seconds depending on number of databases
        - Each database is analyzed independently
        - Continues even if some databases fail
    """
    return await generate_project_insights_service(
        db=db,
        token_payload=token_payload,
        project_id=project_id,
    )


# @backend_router.get(
#     "/business-insights/latest",
#     status_code=status.HTTP_200_OK,
#     response_model=LatestBusinessInsightResponse,
# )
# async def get_latest_business_insight_route(
#     project_id: UUID = Query(..., description="Project ID to filter business insights"),
#     user_id: Optional[UUID] = Query(
#         None, description="User ID to filter (defaults to current user)"
#     ),
#     db: Session = Depends(get_db),
#     token_payload: dict = Depends(get_current_user),
# ):
#     """
#     Fetch the latest generated business insight for a specific user and project.
#     """
#     return await get_latest_business_insight_service(
#         db=db,
#         token_payload=token_payload,
#         project_id=project_id,
#         user_id=user_id,
#     )


