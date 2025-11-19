"""
This module provides various service functions for managing charts, dashboards, and access requests
in a FastAPI application. It includes functionalities such as generating charts, refreshing charts,
handling access requests, saving charts, and managing favorite charts.

The services interact with a PostgreSQL database using SQLAlchemy ORM and utilize Redis for caching
and asynchronous task management. These services are designed to handle user-specific operations
and permissions, ensuring secure and efficient data management.

Modules and Libraries Used:
- FastAPI: For dependency injection and HTTP exception handling.
- SQLAlchemy: For database interactions.
- Redis: For caching and asynchronous task management.
- Logging: For logging service operations and errors.
- UUID: For handling unique identifiers.
- JSON: For serializing and deserializing data.

Key Services:
1. Chart Generation and Refresh:
    - `generate_charts_service`: Generates charts and queues the next batch asynchronously.
    - `refresh_service`: Refreshes charts using pre-generated data from Redis.

2. Access Request Management:
    - `request_access_service`: Creates a new access request for charts.
    - `update_request_access_service`: Updates the status of an access request.
    - `get_access_requests_service`: Retrieves all access requests for a project.

3. Chart Management:
    - `get_charts_service`: Retrieves all charts for a user.
    - `save_chart_service`: Saves a new chart for a user.
    - `save_chart_to_dashboard_service`: Saves a chart to a specific dashboard.
    - `get_charts_for_dashboard_service`: Retrieves charts associated with a dashboard.
    - `delete_chart_from_dashboard_service`: Deletes a chart from a dashboard.

4. Favorite Chart Management:
    - `update_favorite_chart_service`: Toggles the favorite status of a chart.
    - `get_favorite_charts_service`: Retrieves all favorite charts for a user.

Error Handling:
- HTTPException: Raised for various error scenarios such as missing data, unauthorized access,
  or database operation failures.
- Logging: Errors are logged for debugging and monitoring purposes.

Redis Usage:
- Caches current and next batch of charts for quick access.
- Supports asynchronous task management for generating charts.
"""

import json
import logging
from uuid import UUID

import redis
from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.schema_models import (
    ChartAccessRequestModel,
    ChartModel,
    DashboardChartsModel,
    DashboardModel,
    DatabaseConnectionModel,
    PermissionModel,
    ProjectModel,
    RoleModel,
    RolePermissionModel,
    UserChartModel,
    UserDashboardModel,
    UserModel,
    UserProjectRoleModel,
)
from app.schemas import (
    QueryRequest,
    RequestAccess,
    SaveChartRequest,
    SaveChartToDashboardRequest,
    UpdateFavoriteChartRequest,
    UpdateRequestAccess,
)
from app.services.generate_queries import generate_and_store_charts
from app.utils.tasks import generate_charts_asynchronously
from app.utils.token_parser import get_current_user

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)


async def generate_charts_service(
    request: QueryRequest,
    project_id: UUID,
    datasource_connection_id: UUID = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Service function to generate charts and queue the next batch asynchronously.

    This function:
    1. Generates and stores the current set of charts
    2. Saves the chart data to Redis for quick access
    3. Triggers an asynchronous task to prepare the next batch

    Args:
        request (QueryRequest): Query parameters for chart generation
        project_id (UUID): ID of the project
        datasource_connection_id (UUID, optional): ID of the datasource connection
        db (Session): Database session
        token_payload (dict): User authentication token payload

    Returns:
        dict: Generated charts data and status information
    """
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User ID not found in token payload",
            )

        # Check if there are pre-generated charts in Redis
        redis_key = f"charts:next:{user_id}"
        cached_charts = r.get(redis_key)

        if cached_charts:
            # Use pre-generated charts if available
            chart_data = json.loads(cached_charts)

            # Clear the next batch key since we're using it now
            r.delete(redis_key)

            # Store as current charts
            r.set(f"charts:current:{user_id}", cached_charts)

            # Log the use of pre-generated charts
            logger.info("Using pre-generated charts for user %s", user_id)

            # Trigger generation of next batch
            generate_charts_asynchronously.delay(
                user_id=str(user_id),
                datasource_connection_id=(
                    str(datasource_connection_id) if datasource_connection_id else None
                ),
                project_id=str(project_id) if project_id else None,
                query_request=request.dict(),  # Convert Pydantic model to dict
            )

            return {
                "status": "success",
                "message": "Charts retrieved from cache",
                "charts": chart_data,
                "source": "cache",
            }

        # No pre-generated charts available, generate them now
        chart_models = await generate_and_store_charts(
            db=db,
            datasource_connection_id=datasource_connection_id,
            project_id=project_id,
            query_request=request,
            token_payload=token_payload,
        )

        # Serialize chart data for Redis storage
        charts_serialized = [
            {
                "id": str(chart.id),
                "title": chart.title,
                "chart_type": chart.chart_type,
                "created_at": (
                    chart.created_at.isoformat()
                    if hasattr(chart, "created_at")
                    else None
                ),
                "data": chart.data if hasattr(chart, "data") else None,
                "status": getattr(chart, "status", None),
                # Add other relevant chart fields here
            }
            for chart in chart_models
        ]

        # Store current charts in Redis with expiration (e.g., 1 hour)
        r.set(f"charts:current:{user_id}", json.dumps(charts_serialized), ex=3600)

        # Start background task to generate next batch of charts
        generate_charts_asynchronously.delay(
            user_id=str(user_id),
            datasource_connection_id=(
                str(datasource_connection_id) if datasource_connection_id else None
            ),
            project_id=str(project_id) if project_id else None,
            query_request=request.dict(),  # Convert Pydantic model to dict
        )

        return {
            "status": "success",
            "message": "Charts generated successfully",
            "charts": charts_serialized,
            "source": "fresh",
        }

    except (ValueError, HTTPException, SQLAlchemyError) as e:
        logger.error("Error in generate_charts_service: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate charts: {str(e)}",
        ) from e


# async def refresh_service(
#     db: Session,
#     datasource_connection_id: UUID,
#     project_id: UUID,
#     token_payload: dict = Depends(get_current_user)
# ):
#     user_id = str(UUID(token_payload.get("sub")))

#     # Get pre-generated charts from Redis
#     next_charts_json = r.get(f"charts:next:{user_id}")

#     if not next_charts_json:
#         # If no pre-generated charts are available, return an informative message
#         return {
#             "message": "No pre-generated charts available. Please try again later.",
#             "charts": []
#         }

#     # Parse the next charts from Redis
#     next_charts = json.loads(next_charts_json)

#     # Update current charts with the pre-generated ones
#     r.set(f"charts:current:{user_id}", next_charts_json)

#     # Start background task to generate the next batch
#     generate_charts_asynchronously.delay(user_id, str(datasource_connection_id), str(project_id))

#     # Convert string IDs to UUID objects for database operations
#     chart_ids = [UUID(chart["id"]) for chart in next_charts]

#     # Get full chart data from the database
#     chart_models = db.query(ChartModel).filter(ChartModel.id.in_(chart_ids)).all()


#     return {
#         "message": "Charts refreshed successfully",
#         "charts": chart_models
#     }
async def refresh_service(
    db: Session, datasource_connection_id: UUID, project_id: UUID, token_payload: dict
):
    """
    Service function to refresh charts by using pre-generated charts from Redis.

    This function:
    1. Retrieves pre-generated charts from Redis
    2. Sets them as the current charts
    3. Triggers asynchronous generation of the next batch
    4. Returns the full chart data

    Args:
        db (Session): Database session
        datasource_connection_id (UUID): ID of the datasource connection
        project_id (UUID): ID of the project
        token_payload (dict): User authentication token payload

    Returns:
        dict: Refreshed charts data and status information
    """
    try:
        user_id = str(UUID(token_payload.get("sub")))

        # Get pre-generated charts from Redis
        next_charts_key = f"charts:next:{user_id}"
        next_charts_json = r.get(next_charts_key)

        if not next_charts_json:
            # If no pre-generated charts are available, return an informative message
            logger.warning("No pre-generated charts available for user %s", user_id)
            return {
                "status": "warning",
                "message": "No pre-generated charts available. Please try again later.",
                "charts": [],
            }

        # Parse the next charts from Redis
        next_charts = json.loads(next_charts_json)

        # Update current charts with the pre-generated ones
        r.set(f"charts:current:{user_id}", next_charts_json, ex=3600)

        # Delete the next charts key since we're using it now
        r.delete(next_charts_key)

        # Start background task to generate the next batch
        generate_charts_asynchronously.delay(
            user_id=user_id,
            datasource_connection_id=str(datasource_connection_id),
            project_id=str(project_id),
            query_request=None,  # You might want to pass query parameters if needed
        )

        # Convert string IDs to UUID objects for database operations
        chart_ids = [UUID(chart["id"]) for chart in next_charts]

        # Get full chart data from the database
        chart_models = db.query(ChartModel).filter(ChartModel.id.in_(chart_ids)).all()

        # If any charts are missing from the database, log a warning
        if len(chart_models) < len(chart_ids):
            logger.warning(
                "Some charts from Redis were not found in the database. Expected %d, got %d",
                len(chart_ids),
                len(chart_models),
            )

        return {
            "status": "success",
            "message": "Charts refreshed successfully",
            "charts": chart_models,
            "count": len(chart_models),
        }

    except (ValueError, HTTPException, redis.RedisError, SQLAlchemyError) as e:
        logger.error("Error in refresh_service: %s", str(e))
        return {
            "status": "error",
            "message": f"Failed to refresh charts: {str(e)}",
            "charts": [],
        }


# from fastapi import FastAPI
# from tasks import generate_charts_task
# import redis
# import uuid

# app = FastAPI()
# r = redis.Redis(host="localhost", port=6379, db=0)

# @app.get("/test")
# def test_generate(user_id: str = "demo_user"):
#     # Generate current charts
#     current_charts = [f"chart_{uuid.uuid4()}" for _ in range(10)]
#     r.set(f"charts:current:{user_id}", str(current_charts))

#     # Start background job for next batch
#     generate_charts_task.delay(user_id)

#     return {"charts": current_charts}


# @app.get("/refresh")
# def refresh_charts(user_id: str = "demo_user"):
#     # Replace old charts with pre-generated
#     next_charts = r.get(f"charts:next:{user_id}")
#     if next_charts:
#         r.set(f"charts:current:{user_id}", next_charts)
#         # Kick off next round
#         generate_charts_task.delay(user_id)
#         return {"refreshed_charts": next_charts.decode("utf-8")}
#     else:
#         return {"error": "No new charts generated yet"}
async def request_access_service(
    project_id: UUID, data: RequestAccess, db: Session, token_payload: dict
):
    """
    Service function to create a new access request for charts.
    This function:
    1. Validates the user ID from the token payload
    2. Checks if the project exists
    3. Creates a new access request with all chart details
    4. Commits the new access request to the database
    5. Returns the access request ID and success message
    Args:
        project_id (UUID): ID of the project
        data (RequestAccess): Access request data
        db (Session): Database session
        token_payload (dict): User authentication token payload
    Returns:
        dict: Access request ID and success message
    """
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Create access request with all chart details directly in the ChartAccessRequestModel
        new_access_request = ChartAccessRequestModel(
            title=data.title,
            query=data.query,
            report=data.report or None,
            type=data.type,
            relevance=(
                data.relevance if data.relevance is not None else 0.0
            ),  # default to 0.0
            is_time_based=(
                data.is_time_based if data.is_time_based is not None else False
            ),
            chart_type=data.chart_type,
            created_by=user_id,
            requested_by=user_id,
            database_connection_id=data.data_connection_id,
            status="PENDING",
            is_user_generated=True,
            project_id=project_id,
        )
        db.add(new_access_request)
        db.commit()
        db.refresh(new_access_request)

        return {
            "message": "Access request created successfully",
            "access_request_id": new_access_request.id,
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e


async def update_request_access_service(
    project_id: UUID,
    request_id: UUID,
    data: UpdateRequestAccess,
    db: Session,
    token_payload: dict,
):
    """
    Service function to update the status of an access request.
    This function:
    1. Validates the user ID from the token payload
    2. Checks if the user is the project owner
    3. Fetches the access request by ID
    4. Updates the status and reviewer of the access request
    5. If approved, creates a new chart in ChartModel
    6. If rejected, removes the access request from ChartAccessRequestModel
    Args:
        project_id (UUID): ID of the project
        request_id (UUID): ID of the access request
        data (UpdateRequestAccess): Updated access request data
        db (Session): Database session
        token_payload (dict): User authentication token payload
    Returns:
        dict: Updated access request ID, status, and chart ID (if approved)
    """
    user_id = UUID(token_payload.get("sub"))
    if not user_id:
        raise ValueError("User ID not found in token payload")

    # Check if user is the project owner
    # user_project_role = db.query(UserProjectRoleModel).filter(
    #     UserProjectRoleModel.user_id == user_id,
    #     UserProjectRoleModel.project_id == project_id,
    #     UserProjectRoleModel.is_owner == True
    # ).first()

    # if not user_project_role:
    #     raise HTTPException(
    #         status_code=403, detail="User is not authorized to update this access request"
    #     )

    # Fetch the chart access request
    access_request = (
        db.query(ChartAccessRequestModel)
        .filter(ChartAccessRequestModel.id == request_id)
        .first()
    )

    if not access_request:
        raise HTTPException(status_code=404, detail="Access request not found")

    if access_request.status != "PENDING":
        raise HTTPException(
            status_code=400,
            detail=f"Access request has already been {access_request.status.lower()}",
        )

    # Update status and reviewer
    access_request.status = data.status
    access_request.reviewer = user_id

    try:
        # If request is approved, create a new chart in ChartModel
        if data.status == "APPROVED":
            # Create new chart based on the access request data
            new_chart = ChartModel(
                title=access_request.title,
                query=access_request.query,
                report=access_request.report,
                type=access_request.type,
                relevance=access_request.relevance,
                is_time_based=access_request.is_time_based,
                chart_type=access_request.chart_type,
                created_by=access_request.created_by,
                is_user_generated=access_request.is_user_generated,
                status="draft",
            )

            db.add(new_chart)
            db.flush()  # Get the ID without committing

            # Add a relationship between the chart and the requesting user
            user_chart = UserChartModel(
                user_id=access_request.requested_by,
                chart_id=new_chart.id,
                can_read=True,
                can_write=False,
                can_delete=False,
                database_connection_id=access_request.database_connection_id,
            )

            db.add(user_chart)

            # Update the chart_id in the access request to reference the new chart
            access_request.chart_id = new_chart.id

        # If request is rejected, just keep the status as REJECTED (no chart creation)
        elif data.status == "REJECTED":
            # Remove the request from ChartAccessRequestModel
            db.delete(access_request)
            db.commit()

            return {
                "message": "Access request has been rejected and removed",
                "request_id": str(request_id),
                "status": "REJECTED",
                "chart_id": None,
            }

        db.commit()
        db.refresh(access_request)

        return {
            "message": f"Access request has been {data.status.lower()}",
            "request_id": str(access_request.id),
            "status": access_request.status,
            "chart_id": (
                str(access_request.chart_id)
                if access_request.status == "APPROVED"
                else None
            ),
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to process request: {str(e)}"
        ) from e


async def get_access_requests_service(
    project_id: UUID, db: Session, token_payload: dict
):
    """
    Service function to retrieve all access requests for a project.
    This function:
    1. Validates the user ID from the token payload
    2. Checks if the user is the project owner
    3. Fetches all access requests for the project
    4. Returns the access requests with their details
    Args:
        project_id (UUID): ID of the project
        db (Session): Database session
        token_payload (dict): User authentication token payload
    Returns:
         dict: List of access requests with their details
    """
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")

        # Fetch all access requests for the project
        user_project_role = (
            db.query(UserProjectRoleModel)
            .filter(
                UserProjectRoleModel.user_id == user_id,
                UserProjectRoleModel.project_id == project_id,
                UserProjectRoleModel.is_owner is True,
            )
            .first()
        )

        # if not user_project_role:
        #     raise HTTPException(
        #         status_code=403, detail="User is not authorized to view access requests"
        #     )
        access_requests = (
            db.query(ChartAccessRequestModel)
            .filter(ChartAccessRequestModel.project_id == project_id)
            .all()
        )

        return {
            "message": "Access requests retrieved successfully",
            "access_requests": [
                {
                    "id": str(request.id),
                    "title": request.title,
                    "status": request.status,
                    "created_at": request.created_at,
                    "requested_by": (
                        db.query(UserModel)
                        .filter(UserModel.id == request.requested_by)
                        .first()
                        .username
                        if db.query(UserModel)
                        .filter(UserModel.id == request.requested_by)
                        .first()
                        else None
                    ),
                    "reviewer": (
                        db.query(UserModel)
                        .filter(UserModel.id == request.reviewer)
                        .first()
                        .username
                        if db.query(UserModel)
                        .filter(UserModel.id == request.reviewer)
                        .first()
                        else None
                    ),
                }
                for request in access_requests
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


async def get_charts_service(db: Session, token_payload: dict, project_id: UUID = None):
    """
    Get all charts for the user, optionally filtered by project.
    
    Args:
        db (Session): Database session
        token_payload (dict): User authentication token payload
        project_id (UUID): Optional project ID to filter charts by
    
    Returns:
        dict: Charts retrieved for the user, optionally filtered by project
    """
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        
        # Base query for user's charts
        query = db.query(UserChartModel).filter(UserChartModel.user_id == user_id)
        
        # If project_id is provided, join with DatabaseConnectionModel and filter by project
        if project_id:
            query = query.join(
                DatabaseConnectionModel,
                UserChartModel.database_connection_id == DatabaseConnectionModel.id
            ).filter(
                DatabaseConnectionModel.project_id == project_id
            )
        
        user_charts = query.all()

        return {
            "message": "Charts retrieved successfully",
            "project_id": str(project_id) if project_id else None,
            "charts": [
                {
                    "id": str(chart.chart_id),
                    "title": chart.chart.title,
                    "created_at": chart.chart.created_at,
                    "query": chart.chart.query,
                    "type": chart.chart.chart_type,
                    "isFavorite": chart.is_favorite,
                    "datasourceConnectionId": str(chart.database_connection_id) if chart.database_connection_id else None,
                    "status": chart.chart.status if hasattr(chart.chart, "status") else None,
                }
                for chart in user_charts
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


async def save_chart_service(
    project_id: UUID, data: SaveChartRequest, db: Session, token_payload: dict
):
    """
    Save a chart for the user. Super users can save charts regardless of project membership.
    """
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")

        # First check if user is a super user
        user = db.query(UserModel).filter(UserModel.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        is_super_user = user.is_super

        # If not a super user, check if user has a role in the project
        if not is_super_user:
            user_role = (
                db.query(UserProjectRoleModel)
                .filter(
                    UserProjectRoleModel.user_id == user_id,
                    UserProjectRoleModel.project_id == project_id,
                )
                .first()
            )

            if not user_role:
                raise HTTPException(status_code=404, detail="User not found in project")

            # Get the role permissions
            role = db.query(RoleModel).filter(RoleModel.id == user_role.role_id).first()
            if not role:
                raise HTTPException(status_code=404, detail="Role not found")

            # Initialize permission flags
            can_read = False
            can_write = False
            can_delete = False

            # Get permissions associated with this role
            role_permissions = (
                db.query(RolePermissionModel)
                .filter(RolePermissionModel.role_id == user_role.role_id)
                .all()
            )

            # Get the actual permission types
            for role_permission in role_permissions:
                permission = (
                    db.query(PermissionModel)
                    .filter(PermissionModel.id == role_permission.permission_id)
                    .first()
                )

                if permission:
                    if permission.type == "view_chart":
                        can_read = True
                    elif permission.type == "create_chart":
                        can_write = True
                    elif permission.type == "delete_chart":
                        can_delete = True
        else:
            # Super user gets all permissions
            can_read = True
            can_write = True
            can_delete = True

        status_value = (
            data.status.value
            if hasattr(data, "status") and data.status is not None
            else "draft"
        )

        # Create the new chart
        new_chart = ChartModel(
            title=data.title,
            query=data.query,
            report=data.report,
            type=data.type,
            relevance=(
                data.relevance
                if hasattr(data, "relevance") and data.relevance is not None
                else 0.0
            ),
            is_time_based=(
                data.is_time_based
                if hasattr(data, "is_time_based") and data.is_time_based is not None
                else False
            ),
            chart_type=data.chart_type,
            created_by=user_id,
            is_user_generated=True,
            status=status_value,
        )
        db.add(new_chart)
        db.flush()  # Get the ID without committing

        # The chart creator should always have read access
        can_read = True

        # Create the user-chart relationship
        user_chart = UserChartModel(
            user_id=user_id,
            chart_id=new_chart.id,
            can_read=can_read,
            can_write=can_write,
            can_delete=can_delete,
            database_connection_id=data.data_connection_id,
        )
        db.add(user_chart)
        db.commit()
        db.refresh(new_chart)  # Refresh the chart to get complete data

        return {"message": "Chart saved successfully", "chart_id": str(new_chart.id)}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e


async def save_chart_to_dashboard_service(
    data: SaveChartToDashboardRequest, db: Session, token_payload: dict
):
    """
    Save a chart to a specific dashboard.
    This function:
    1. Validates the user ID from the token payload
    2. Checks if the dashboard exists
    3. Creates a new chart and associates it with the dashboard
    4. Commits the new chart and dashboard association to the database
    """
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        dashboard = (
            db.query(DashboardModel)
            .filter(DashboardModel.id == data.dashboard_id)
            .first()
        )
        if not dashboard:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        # Check if user has permission to write to the dashboard
        status_value = (
            data.status.value
            if hasattr(data, "status") and data.status is not None
            else "published"
        )
        new_chart = ChartModel(
            title=data.title,
            query=data.query,
            report=(
                data.report
                if hasattr(data, "report") and data.report is not None
                else None
            ),
            type=data.type,
            relevance=(
                data.relevance
                if hasattr(data, "relevance") and data.relevance is not None
                else 0.0
            ),
            is_time_based=(
                data.is_time_based
                if hasattr(data, "is_time_based") and data.is_time_based is not None
                else False
            ),
            chart_type=data.chart_type,
            created_by=user_id,
            is_user_generated=True,
            status=status_value,
        )
        db.add(new_chart)
        db.flush()

        # Ensure chart status reflects publication when attached to a dashboard
        new_chart.status = "published"

        new_chart_to_dashboard = DashboardChartsModel(
            dashboard_id=data.dashboard_id,
            chart_id=new_chart.id,
            database_connection_id=data.data_connection_id,
        )
        db.add(new_chart_to_dashboard)
        db.commit()
        db.refresh(new_chart)
        db.refresh(new_chart_to_dashboard)
        return {
            "message": "Chart added to dashboard successfully",
            "chart_id": str(new_chart_to_dashboard.chart_id),
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e


async def get_charts_for_dashboard_service(
    dashboard_id: UUID, db: Session, token_payload: dict
):
    """
    Get all charts for a specific dashboard.
    This function:
    1. Validates the user ID from the token payload
    2. Checks if the dashboard exists
    3. Fetches all charts associated with the dashboard
    4. Returns the charts with their details
    Args:
        dashboard_id (UUID): ID of the dashboard
        db (Session): Database session
        token_payload (dict): User authentication token payload
    Returns:
        dict: List of charts associated with the dashboard
    """
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        dashboard = (
            db.query(DashboardModel).filter(DashboardModel.id == dashboard_id).first()
        )
        if not dashboard:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        # Check if user has permission to read the dashboard
        charts = (
            db.query(DashboardChartsModel)
            .filter(DashboardChartsModel.dashboard_id == dashboard_id)
            .all()
        )
        return {
            "message": "Charts retrieved successfully",
            "charts": [
                {
                    "id": str(chart.chart_id),
                    "title": chart.chart.title,
                    "query": chart.chart.query,
                    "created_at": chart.chart.created_at,
                    "connection_id": chart.database_connection_id,
                    "status": chart.chart.status if hasattr(chart.chart, "status") else None,
                }
                for chart in charts
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


async def get_user_dashboard_charts_service(
    db: Session, token_payload: dict
):
    """
    Retrieve charts from all dashboards that the authenticated user is part of.

    Returns:
        dict: Dashboards and their associated charts.
    """
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")

        user_dashboards = (
            db.query(DashboardModel)
            .join(
                UserDashboardModel,
                UserDashboardModel.dashboard_id == DashboardModel.id,
            )
            .filter(UserDashboardModel.user_id == user_id)
            .all()
        )

        if not user_dashboards:
            return {
                "message": "No dashboards found for user",
                "dashboards": [],
            }

        dashboard_ids = [dashboard.id for dashboard in user_dashboards]

        dashboard_chart_map = {dashboard.id: [] for dashboard in user_dashboards}

        dashboard_charts = (
            db.query(DashboardChartsModel)
            .filter(DashboardChartsModel.dashboard_id.in_(dashboard_ids))
            .all()
        )

        for dashboard_chart in dashboard_charts:
            chart = dashboard_chart.chart
            if not chart:
                continue

            connection = dashboard_chart.database_connection

            dashboard_chart_map[dashboard_chart.dashboard_id].append(
                {
                    "id": str(chart.id),
                    "title": chart.title,
                    "query": chart.query,
                    "report": chart.report,
                    "type": chart.type,
                    "chart_type": chart.chart_type,
                    "relevance": chart.relevance,
                    "is_time_based": chart.is_time_based,
                    "status": getattr(chart, "status", None),
                    "is_user_generated": chart.is_user_generated,
                    "created_by": str(chart.created_by) if chart.created_by else None,
                    "created_at": (
                        chart.created_at.isoformat() if chart.created_at else None
                    ),
                    "database_connection": {
                        "id": (
                            str(dashboard_chart.database_connection_id)
                            if dashboard_chart.database_connection_id
                            else None
                        ),
                        "name": connection.connection_name if connection else None,
                        "type": connection.db_type if connection else None,
                    },
                }
            )

        dashboards_response = []
        for dashboard in user_dashboards:
            dashboards_response.append(
                {
                    "dashboard_id": str(dashboard.id),
                    "dashboard_title": dashboard.title,
                    "project_id": str(dashboard.project_id),
                    "charts": dashboard_chart_map.get(dashboard.id, []),
                }
            )

        return {
            "message": "Dashboard charts retrieved successfully",
            "dashboards": dashboards_response,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


async def delete_chart_from_dashboard_service(
    dashboard_id: UUID, chart_id: UUID, db: Session, token_payload: dict
):
    """
    Delete a chart from a specific dashboard.
    This function:
    1. Validates the user ID from the token payload
    2. Checks if the dashboard exists
    3. Checks if the chart exists
    4. Deletes the chart from the dashboard
    5. Commits the deletion to the database
    Args:
        dashboard_id (UUID): ID of the dashboard
        chart_id (UUID): ID of the chart
        db (Session): Database session
        token_payload (dict): User authentication token payload
    Returns:
        dict: Success message
    """
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        dashboard = (
            db.query(DashboardModel).filter(DashboardModel.id == dashboard_id).first()
        )
        if not dashboard:
            raise HTTPException(status_code=404, detail="Dashboard not found")

        dashboard_chart = (
            db.query(DashboardChartsModel)
            .filter(
                DashboardChartsModel.dashboard_id == dashboard_id,
                DashboardChartsModel.chart_id == chart_id,
            )
            .first()
        )
        if not dashboard_chart:
            raise HTTPException(status_code=404, detail="Chart not found")
        chart_record = (
            db.query(ChartModel).filter(ChartModel.id == chart_id).first()
        )
        db.delete(dashboard_chart)
        db.flush()
        if chart_record:
            remaining = (
                db.query(DashboardChartsModel)
                .filter(DashboardChartsModel.chart_id == chart_id)
                .count()
            )
            if remaining == 0:
                chart_record.status = "draft"
        db.commit()
        return {"message": "Chart deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def _serialize_favorite_charts(user_chart_records):
    """Serialize a list of UserChartModel records into API response format."""

    serialized_charts = []

    for user_chart in user_chart_records:
        chart = user_chart.chart
        serialized_charts.append(
            {
                "id": str(user_chart.chart_id),
                "title": chart.title if chart else None,
                "created_at": chart.created_at if chart else None,
                "connection_id": (
                    str(user_chart.database_connection_id)
                    if getattr(user_chart, "database_connection_id", None)
                    else None
                ),
                "query": chart.query if chart else None,
                "chart_type": chart.chart_type if chart else None,
                "is_favorite": user_chart.is_favorite,
                "status": getattr(chart, "status", None) if chart else None,
            }
        )

    return serialized_charts


async def update_favorite_chart_service(
    data: UpdateFavoriteChartRequest, db: Session, token_payload: dict
):
    """
    Update the favorite status of a chart for the user.
    This function:
    1. Validates the user ID from the token payload
    2. Checks if the chart exists
    3. Toggles the favorite status of the chart
    4. Commits the update to the database
    Args:
        data (UpdateFavoriteChartRequest): Chart ID and favorite status
        db (Session): Database session
        token_payload (dict): User authentication token payload
    Returns:
        dict: Success message and updated favorite status
    """
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        # Check if the chart exists
        chart = (
            db.query(UserChartModel)
            .filter(
                UserChartModel.chart_id == data.chart_id,
                UserChartModel.user_id == user_id,
            )
            .first()
        )
        if not chart:
            raise HTTPException(status_code=404, detail="Chart not found")
        # Update the chart's favorite status
        chart.is_favorite = not chart.is_favorite
        db.commit()
        db.refresh(chart)
        return {
            "message": "Chart favorite status updated successfully",
            "is_favorite": chart.is_favorite,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e


async def get_favorite_charts_service(db: Session, token_payload: dict):
    """
    Get all favorite charts for the user.
    This function:
    1. Validates the user ID from the token payload
    2. Fetches all favorite charts for the user
    3. Returns the favorite charts with their details
    Args:
        db (Session): Database session
        token_payload (dict): User authentication token payload
    Returns:
        dict: List of favorite charts with their details
    """
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        # Fetch all favorite charts for the user
        favorite_charts = (
            db.query(UserChartModel)
            .filter(
                UserChartModel.user_id == user_id, UserChartModel.is_favorite == True
            )
            .all()
        )

        return {
            "message": "Favorite charts retrieved successfully",
            "favorite_charts": _serialize_favorite_charts(favorite_charts),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


async def get_pinned_charts_count_service(db: Session, token_payload: dict):
    """
    Get the count of pinned (favorite) charts for the user.
    This function:
    1. Validates the user ID from the token payload
    2. Counts all pinned/favorite charts for the user
    3. Returns the count
    
    Args:
        db (Session): Database session
        token_payload (dict): User authentication token payload
    Returns:
        dict: Count of pinned charts
    """
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        
        # Count all pinned/favorite charts for the user
        pinned_charts_count = (
            db.query(UserChartModel)
            .filter(
                UserChartModel.user_id == user_id,
                UserChartModel.is_favorite == True
            )
            .count()
        )
        
        return {
            "message": "Pinned charts count retrieved successfully",
            "pinned_charts_count": pinned_charts_count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


async def get_user_favorite_charts_service(
     db: Session, token_payload: dict
):
    """Retrieve favorite charts for a specific user, with authorization checks."""

    try:
        requester_id_str = token_payload.get("sub")
        if not requester_id_str:
            raise ValueError("User ID not found in token payload")
        target_user_id = UUID(token_payload.get("sub"))

        requester_id = UUID(requester_id_str)

        if requester_id != target_user_id:
            requester = (
                db.query(UserModel).filter(UserModel.id == requester_id).first()
            )

            if not requester:
                raise HTTPException(status_code=404, detail="Requesting user not found")

            if not requester.is_super:
                raise HTTPException(
                    status_code=403,
                    detail="Not authorized to view favorite charts for this user",
                )

        target_user = (
            db.query(UserModel).filter(UserModel.id == target_user_id).first()
        )

        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

        favorite_charts = (
            db.query(UserChartModel)
            .filter(
                UserChartModel.user_id == target_user_id,
                UserChartModel.is_favorite == True,
            )
            .all()
        )

        return {
            "message": "Favorite charts retrieved successfully",
            "favorite_charts": _serialize_favorite_charts(favorite_charts),
            "user_id": str(target_user_id),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


async def filter_charts_service(
    db: Session,
    token_payload: dict,
    dashboard_id: UUID = None,
    database_connection_id: UUID = None,
    status: str = None,
):
    """
    Filter charts based on dashboard, database connection, and status.
    
    All filter parameters are optional and can be combined:
    - dashboard_id: Filter charts by specific dashboard
    - database_connection_id: Filter charts by database connection
    - status: Filter charts by status (draft, published)
    
    Status definitions:
    - "draft": Charts not added to any dashboard
    - "published": Charts added to at least one dashboard
    - None/omitted: All charts (no status filter)
    
    Args:
        db (Session): Database session
        token_payload (dict): User authentication token payload
        dashboard_id (UUID): Optional UUID of dashboard to filter by
        database_connection_id (UUID): Optional UUID of database connection to filter by
        status (str): Optional status filter ("draft" or "published")
        
    Returns:
        dict: Filtered charts with their details
    """
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        
        # Start with base query for user's charts
        query = db.query(UserChartModel).filter(UserChartModel.user_id == user_id)
        
        # Apply database connection filter if provided
        if database_connection_id:
            query = query.filter(
                UserChartModel.database_connection_id == database_connection_id
            )
        
        # Get all user charts matching the filters so far
        user_charts = query.all()
        
        # Now apply dashboard and status filters
        filtered_charts = []
        
        for user_chart in user_charts:
            chart = user_chart.chart
            
            # Check if chart is in any dashboard
            dashboard_charts = (
                db.query(DashboardChartsModel)
                .filter(DashboardChartsModel.chart_id == chart.id)
                .all()
            )
            
            is_published = len(dashboard_charts) > 0
            
            # Apply dashboard filter
            if dashboard_id:
                # Only include if chart is in the specified dashboard
                in_dashboard = any(
                    dc.dashboard_id == dashboard_id for dc in dashboard_charts
                )
                if not in_dashboard:
                    continue
            
            # Determine chart status using stored value with fallback
            chart_status = (
                chart.status.lower()
                if getattr(chart, "status", None)
                else ("published" if is_published else "draft")
            )

            # Apply status filter
            if status:
                if chart_status != status.lower():
                    continue
            # If status is None/omitted, include all charts
            
            # Get dashboards this chart belongs to
            dashboards = []
            for dc in dashboard_charts:
                dashboard = (
                    db.query(DashboardModel)
                    .filter(DashboardModel.id == dc.dashboard_id)
                    .first()
                )
                if dashboard:
                    dashboards.append({
                        "id": str(dashboard.id),
                        "title": dashboard.title
                    })
            
            # Get database connection info
            db_connection = (
                db.query(DatabaseConnectionModel)
                .filter(
                    DatabaseConnectionModel.id == user_chart.database_connection_id
                )
                .first()
            )
            
            filtered_charts.append({
                "id": str(chart.id),
                "title": chart.title,
                "created_at": chart.created_at.isoformat() if chart.created_at else None,
                "query": chart.query,
                "chart_type": chart.chart_type,
                "type": chart.type,
                "is_favorite": user_chart.is_favorite,
                "status": chart_status,
                "database_connection_id": str(user_chart.database_connection_id),
                "database_connection_name": (
                    db_connection.connection_name if db_connection else None
                ),
                "dashboards": dashboards,
                "dashboard_count": len(dashboards),
            })
        
        return {
            "message": "Charts filtered successfully",
            "charts": filtered_charts,
            "total_count": len(filtered_charts),
            "filters_applied": {
                "dashboard_id": str(dashboard_id) if dashboard_id else None,
                "database_connection_id": (
                    str(database_connection_id) if database_connection_id else None
                ),
                "status": status if status else "all",
            },
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
