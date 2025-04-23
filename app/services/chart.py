
import json
from uuid import UUID
from app.utils.tasks import generate_charts_asynchronously
from app.schemas import (RequestAccess, UpdateRequestAccess,SaveChartRequest,SaveChartToDashboardRequest,QueryRequest,
UpdateFavoriteChartRequest)
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.schema_models import (ChartAccessRequestModel, DashboardChartsModel, ProjectModel, UserProjectRoleModel,ChartModel,
    UserChartModel,RoleModel,RolePermissionModel,PermissionModel,UserModel,DashboardModel)
from app.services.generate_queries import generate_and_store_charts
from typing import Union

from sqlalchemy.orm import Session
from app.core.db import get_db
from fastapi import Depends,status
from app.utils.token_parser import get_current_user
from typing import Optional
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
import redis

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
                detail="User ID not found in token payload"
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
            logger.info(f"Using pre-generated charts for user {user_id}")
            
            # Trigger generation of next batch
            generate_charts_asynchronously.delay(
                user_id=str(user_id),
                datasource_connection_id=str(datasource_connection_id) if datasource_connection_id else None,
                project_id=str(project_id) if project_id else None,
                query_request=request.dict()  # Convert Pydantic model to dict
            )
            
            return {
                "status": "success",
                "message": "Charts retrieved from cache",
                "charts": chart_data,
                "source": "cache"
            }
        
        # No pre-generated charts available, generate them now
        chart_models = await generate_and_store_charts(
            db=db,
            datasource_connection_id=datasource_connection_id,
            project_id=project_id,
            query_request=request,
            token_payload=token_payload
        )
        
        # Serialize chart data for Redis storage
        charts_serialized = [{
            "id": str(chart.id),
            "title": chart.title,
            "chart_type": chart.chart_type,
            "created_at": chart.created_at.isoformat() if hasattr(chart, 'created_at') else None,
            "data": chart.data if hasattr(chart, 'data') else None,
            # Add other relevant chart fields here
        } for chart in chart_models]
        
        # Store current charts in Redis with expiration (e.g., 1 hour)
        r.set(f"charts:current:{user_id}", json.dumps(charts_serialized), ex=3600)
        
        # Start background task to generate next batch of charts
        generate_charts_asynchronously.delay(
            user_id=str(user_id),
            datasource_connection_id=str(datasource_connection_id) if datasource_connection_id else None,
            project_id=str(project_id) if project_id else None,
            query_request=request.dict() # Convert Pydantic model to dict
        )
        
        return {
            "status": "success",
            "message": "Charts generated successfully",
            "charts": charts_serialized,
            "source": "fresh"
        }
        
    except Exception as e:
        logger.error(f"Error in generate_charts_service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate charts: {str(e)}"
        )

        
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
    db: Session,
    datasource_connection_id: UUID,
    project_id: UUID,
    token_payload: dict
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
            logger.warning(f"No pre-generated charts available for user {user_id}")
            return {
                "status": "warning",
                "message": "No pre-generated charts available. Please try again later.",
                "charts": []
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
            query_request=None  # You might want to pass query parameters if needed
        )
        
        # Convert string IDs to UUID objects for database operations
        chart_ids = [UUID(chart["id"]) for chart in next_charts]
        
        # Get full chart data from the database
        chart_models = db.query(ChartModel).filter(ChartModel.id.in_(chart_ids)).all()
        
        # If any charts are missing from the database, log a warning
        if len(chart_models) < len(chart_ids):
            logger.warning(f"Some charts from Redis were not found in the database. Expected {len(chart_ids)}, got {len(chart_models)}")
        
        return {
            "status": "success",
            "message": "Charts refreshed successfully",
            "charts": chart_models,
            "count": len(chart_models)
        }
        
    except Exception as e:
        logger.error(f"Error in refresh_service: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to refresh charts: {str(e)}",
            "charts": []
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
    project_id: UUID, 
    data: RequestAccess,
    db: Session,
    token_payload: dict
):
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        project=db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Create access request with all chart details directly in the ChartAccessRequestModel
        new_access_request = ChartAccessRequestModel(
            title=data.title,
            query=data.query,
            report=data.report or None,
            type=data.type,
            relevance=data.relevance if data.relevance is not None else 0.0,  # default to 0.0
            is_time_based=data.is_time_based if data.is_time_based is not None else False,
            chart_type=data.chart_type,
            created_by=user_id,
            requested_by=user_id,
            status="PENDING",
            is_user_generated=True,
            project_id=project_id
            
        )
        db.add(new_access_request)
        db.commit()
        db.refresh(new_access_request)

        return {
            "message": "Access request created successfully",
            "access_request_id": new_access_request.id
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


async def update_request_access_service(
    project_id: UUID,
    request_id: UUID,
    data: UpdateRequestAccess,
    db: Session,
    token_payload: dict,
):
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
    access_request = db.query(ChartAccessRequestModel).filter(
        ChartAccessRequestModel.id == request_id
    ).first()
    
    if not access_request:
        raise HTTPException(status_code=404, detail="Access request not found")
    
    if access_request.status != "PENDING":
        raise HTTPException(
            status_code=400, 
            detail=f"Access request has already been {access_request.status.lower()}"
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
                is_user_generated=access_request.is_user_generated
            )
            
            db.add(new_chart)
            db.flush()  # Get the ID without committing
            
            # Add a relationship between the chart and the requesting user
            user_chart = UserChartModel(
                user_id=access_request.requested_by,
                chart_id=new_chart.id,
                can_read=True,
                can_write=False,
                can_delete=False
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
                "chart_id": None
            }
        
        db.commit()
        db.refresh(access_request)
        
        return {
            "message": f"Access request has been {data.status.lower()}",
            "request_id": str(access_request.id),
            "status": access_request.status,
            "chart_id": str(access_request.chart_id) if access_request.status == "APPROVED" else None
        }
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to process request: {str(e)}")

async def get_access_requests_service(
    project_id: UUID,
    db: Session,
    token_payload: dict
    
):
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        # Fetch all access requests for the project
        user_project_role = db.query(UserProjectRoleModel).filter(
            UserProjectRoleModel.user_id == user_id,
            UserProjectRoleModel.project_id == project_id,
            UserProjectRoleModel.is_owner == True
        ).first()


        # if not user_project_role:
        #     raise HTTPException(
        #         status_code=403, detail="User is not authorized to view access requests"
        #     )
        access_requests = db.query(ChartAccessRequestModel).filter(
            ChartAccessRequestModel.project_id == project_id
        ).all()
        return {
            "message": "Access requests retrieved successfully",
            "access_requests": [
                {
                    "id": str(request.id),
                    "title": request.title,
                    "status": request.status,
                    "created_at": request.created_at
                } for request in access_requests
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def get_charts_service(
    db: Session,
    token_payload: dict
):
    """
    Get all charts for the user.(Currently retrieves all charts, in userCharts table)
    """
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        # Fetch all charts for the user
        user_charts = db.query(UserChartModel).filter(
            UserChartModel.user_id == user_id
        ).all()

        return {
            "message": "Charts retrieved successfully",
            "charts": [
                {
                    "id": str(chart.chart_id),
                    "title": chart.chart.title,
                    "created_at": chart.chart.created_at
                } for chart in user_charts
            ]
            
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def save_chart_service(
    project_id: UUID,
    data: SaveChartRequest,
    db: Session,
    token_payload: dict
):
    """
    Save a chart for the user. Super users can save charts regardless of project membership.
    """
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        
        # First check if user is a super user
        user = db.query(UserModel).filter(
            UserModel.id == user_id
        ).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        is_super_user = user.is_super 
        
        # If not a super user, check if user has a role in the project
        if not is_super_user:
            user_role = db.query(UserProjectRoleModel).filter(
                UserProjectRoleModel.user_id == user_id,
                UserProjectRoleModel.project_id == project_id
            ).first()
            
            if not user_role:
                raise HTTPException(status_code=404, detail="User not found in project")

            # Get the role permissions
            role = db.query(RoleModel).filter(
                RoleModel.id == user_role.role_id
            ).first()
            if not role:
                raise HTTPException(status_code=404, detail="Role not found")
            
            # Initialize permission flags
            can_read = False
            can_write = False
            can_delete = False
            
            # Get permissions associated with this role
            role_permissions = db.query(RolePermissionModel).filter(
                RolePermissionModel.role_id == user_role.role_id
            ).all()
            
            # Get the actual permission types
            for role_permission in role_permissions:
                permission = db.query(PermissionModel).filter(
                    PermissionModel.id == role_permission.permission_id
                ).first()
                
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

        # Create the new chart
        new_chart = ChartModel(
            title=data.title,
            query=data.query,
            report=data.report,
            type=data.type,
            relevance=data.relevance if hasattr(data, 'relevance') and data.relevance is not None else 0.0,
            is_time_based=data.is_time_based if hasattr(data, 'is_time_based') and data.is_time_based is not None else False,
            chart_type=data.chart_type,
            created_by=user_id,
            is_user_generated=True,

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
            can_delete=can_delete
        )
        db.add(user_chart)
        db.commit()
        db.refresh(new_chart)  # Refresh the chart to get complete data
        
        return {
            "message": "Chart saved successfully",
            "chart_id": str(new_chart.id)
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
async def save_chart_to_dashboard_service(
    data:SaveChartToDashboardRequest,
    db:Session,
    token_payload:dict
):
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        dashboard=db.query(DashboardModel).filter(DashboardModel.id==data.dashboard_id).first()
        if not dashboard:
            raise HTTPException(status_code=404,detail="Dashboard not found")
        # Check if user has permission to write to the dashboard
        new_chart = ChartModel(
            title=data.title,
            query=data.query,
            report=data.report if hasattr(data,'report') and data.report is not None else None,
            type=data.type,
            relevance=data.relevance if hasattr(data, 'relevance') and data.relevance is not None else 0.0,
            is_time_based=data.is_time_based if hasattr(data, 'is_time_based') and data.is_time_based is not None else False,
            chart_type=data.chart_type,
            created_by=user_id,
            is_user_generated=True,

        )
        db.add(new_chart)
        db.flush()
        db.refresh(new_chart)
        new_chart_to_dashboard=DashboardChartsModel(
            dashboard_id=data.dashboard_id,
            chart_id=new_chart.id,
            
        )
        db.add(new_chart_to_dashboard)
        db.commit()
        db.refresh(new_chart_to_dashboard)
        return {
            "message": "Chart added to dashboard successfully",
            "chart_id": str(new_chart_to_dashboard.chart_id)
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500,detail=str(e))

async def get_charts_for_dashboard_service(
    dashboard_id:UUID,
    db:Session,
    token_payload:dict
):
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        dashboard=db.query(DashboardModel).filter(DashboardModel.id==dashboard_id).first()
        if not dashboard:
            raise HTTPException(status_code=404,detail="Dashboard not found")
        # Check if user has permission to read the dashboard
        charts=db.query(DashboardChartsModel).filter(DashboardChartsModel.dashboard_id==dashboard_id).all()
        return {
            "message": "Charts retrieved successfully",
            "charts": [
                {
                    "id": str(chart.chart_id),
                    "title": chart.chart.title,
                    "created_at": chart.chart.created_at
                } for chart in charts
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500,detail=str(e))

async def delete_chart_from_dashboard_service(
    dashboard_id:UUID,
    chart_id:UUID,
    db:Session,
    token_payload:dict
):
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        dashboard=db.query(DashboardModel).filter(DashboardModel.id==dashboard_id).first()
        if not dashboard:
            raise HTTPException(status_code=404,detail="Dashboard not found")

        chart=db.query(DashboardChartsModel).filter(DashboardChartsModel.dashboard_id==dashboard_id,DashboardChartsModel.chart_id==chart_id).first()
        if not chart:
            raise HTTPException(status_code=404,detail="Chart not found")
        db.delete(chart)
        db.commit()
        return {
            "message": "Chart deleted successfully"

        }
    except Exception as e:
        raise HTTPException(status_code=500,detail=str(e))

async def update_favorite_chart_service(
     data: UpdateFavoriteChartRequest,
    db: Session,
    token_payload: dict
):
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        # Check if the chart exists
        chart = db.query(UserChartModel).filter(UserChartModel.chart_id == data.chart_id, UserChartModel.user_id==user_id).first()
        if not chart:
            raise HTTPException(status_code=404, detail="Chart not found")
        # Update the chart's favorite status
        chart.is_favorite = not chart.is_favorite
        db.commit()
        db.refresh(chart)
        return {
            "message": "Chart favorite status updated successfully",
            "is_favorite": chart.is_favorite
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

async def get_favorite_charts_service(
    db: Session,
    token_payload: dict
):
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise ValueError("User ID not found in token payload")
        # Fetch all favorite charts for the user
        favorite_charts = db.query(UserChartModel).filter(UserChartModel.user_id == user_id, UserChartModel.is_favorite == True).all()
        return {
            "message": "Favorite charts retrieved successfully",
            "favorite_charts": [
                {
                    "id": str(chart.chart_id),
                    "title": chart.chart.title,
                    "created_at": chart.chart.created_at
                } for chart in favorite_charts
            ]   
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
