
from hmac import new
from uuid import UUID
from app.utils.tasks import generate_charts_asynchronously
from app.schemas import (RequestAccess, UpdateRequestAccess,SaveChartRequest,SaveChartToDashboardRequest)
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.schema_models import (ChartAccessRequestModel, DashboardChartsModel, ProjectModel, UserProjectRoleModel,ChartModel,
    UserChartModel,RoleModel,RolePermissionModel,PermissionModel,UserModel,DashboardModel)
 # assuming this has a `status` field


async def generate_charts_service():

   
        #write code to generate first set of charts
        #r.set('charts', charts)
        # generate_charts_asynchronously.delay()
        #return first set of charts
        pass
async def refresh_service():
    #write code to replace old charts wirh new charts
    #rerun generate_charts_asynchronously.delay()
    # return new charts
    pass


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