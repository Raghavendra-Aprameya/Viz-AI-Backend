from functools import wraps
import inspect
from sqlalchemy import true
from app.models.schema_models import UserProjectRoleModel,UserDashboardModel,UserChartModel,PermissionModel,RolePermissionModel,UserModel
from app.utils.token_parser import get_current_user
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional
from app.models.permissions import Permissions as Permission
def check_dashboard_access(db: Session, project_id:UUID,dashboard_id:UUID,action:str):
    try: 
        user_id = UUID(get_current_user(db).get("sub"))
        user_project_role = db.query(UserProjectRoleModel).filter(UserProjectRoleModel.user_id == user_id, UserProjectRoleModel.project_id == project_id).first()
        if not user_project_role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to this project")
        user_access = db.query(UserDashboardModel).filter(UserDashboardModel.user_id == user_id,UserDashboardModel.dashboard_id == dashboard_id).first()
        if not user_access:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to this dashboard")
        
        if action == "read":
            if user_access.can_read == False:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have read access to this dashboard")
            else:
                return True
        if action == "write":
            if user_access.can_write == False:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have write access to this dashboard")
            else:
                return True
        if action == "delete":
            if user_access.can_delete == False:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have delete access to this dashboard")
            else:
                return True
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

 
def check_chart_access(db: Session, project_id:UUID, chart_id:UUID, action:str):
  try:
    user_id = UUID(get_current_user(db).get("sub"))
    user_project_role = db.query(UserProjectRoleModel).filter(UserProjectRoleModel.user_id == user_id, UserProjectRoleModel.project_id == project_id).first()
    if not user_project_role:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to this project")
    
    user_access = db.query(UserChartModel).filter(UserChartModel.user_id == user_id,UserChartModel.chart_id == chart_id).first()
    if not user_access:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to this chart")
    
    if action == "read":
      if user_access.can_read == False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have read access to this chart")
      else:
        return True
    if action == "write":
      if user_access.can_write == False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have write access to this chart")
      else:
        return True
    if action == "delete":
      if user_access.can_delete == False:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have delete access to this chart")
      else:
        return True
  except Exception as e:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
  
async def check_project_create_access(db: Session, token_payload:dict):
    try:
        user_id = UUID(token_payload.get("sub"))
        user_project_roles = db.query(UserProjectRoleModel).filter(UserProjectRoleModel.user_id == user_id).all()
        
        if not user_project_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have any roles assigned")

        # Check if any role has the required permission
        for user_project_role in user_project_roles:
            role_permission = db.query(RolePermissionModel).filter(
                RolePermissionModel.role_id == user_project_role.role_id,
                RolePermissionModel.permission_id == "8e1c6f1e-7c99-4f28-bd2e-c7b79d6122c1"
            ).first()
            
            if role_permission:
                return True
                
        # If we get here, no role had the required permission
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have permission to create projects")

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

# def check_project_delete_access(db: Session, project_id:UUID):
#   try:
#     user_id = UUID(get_current_user(db).get("sub"))
#     user_project_role = db.query(UserProjectRoleModel).filter(UserProjectRoleModel.user_id == user_id, UserProjectRoleModel.project_id == project_id).first()
#     if not user_project_role:
#       raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to this project")
    
  
async def check_create_role_access(db: Session, project_id:UUID,token_payload:dict):
  try:
    user_id = UUID(token_payload.get("sub"))
    user_project_role = db.query(UserProjectRoleModel).filter(UserProjectRoleModel.user_id == user_id, UserProjectRoleModel.project_id == project_id).first()
    if not user_project_role:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to this project")
    role_permission = db.query(RolePermissionModel).filter(RolePermissionModel.role_id == user_project_role.role_id, RolePermissionModel.permission_id == "6e073b1d-f56c-4a6e-8a9d-2cb37a4702a4").first()
    if not role_permission:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to create role")
    else:
      return True
  except Exception as e:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

async def check_add_db_connection_access(db: Session, token_payload:dict,project_id:UUID):
  try:
    user_id = UUID(token_payload.get("sub"))
    user_project_role = db.query(UserProjectRoleModel).filter(UserProjectRoleModel.user_id == user_id,UserProjectRoleModel.project_id == project_id).first()
    if not user_project_role:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to this project")
    role_permission = db.query(RolePermissionModel).filter(RolePermissionModel.role_id == user_project_role.role_id, RolePermissionModel.permission_id == "f11a63e3-fc6e-4d36-aeae-943d118c3e27").first()
    if not role_permission:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to add db connection")
    else:

      return True
  except Exception as e:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) 
  
async def check_add_user_access(db: Session, token_payload:dict,project_id:UUID):
  try:
    user_id = UUID(token_payload.get("sub"))
    user_project_role = db.query(UserProjectRoleModel).filter(UserProjectRoleModel.user_id == user_id,UserProjectRoleModel.project_id == project_id).first()
    if not user_project_role:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to this project")
    role_permission = db.query(RolePermissionModel).filter(RolePermissionModel.role_id == user_project_role.role_id, RolePermissionModel.permission_id == "6e073b1d-f56c-4a6e-8a9d-2cb37a4702a5").first()
    if not role_permission:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to add user")
    else:
      return True
  except Exception as e:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) 

async def check_dashboard_create_access(db: Session, token_payload:dict,project_id:UUID):
  try:
    user_id = UUID(token_payload.get("sub"))
    user_project_role = db.query(UserProjectRoleModel).filter(UserProjectRoleModel.user_id == user_id,UserProjectRoleModel.project_id == project_id).first()
    if not user_project_role:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to this project")
    role_permission = db.query(RolePermissionModel).filter(RolePermissionModel.role_id == user_project_role.role_id, RolePermissionModel.permission_id == "6e073b1d-f56c-4a6e-8a9d-2cb37a4702a7").first()
    if not role_permission:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to create dashboard")
    else:
      return True
  except Exception as e:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) 
  
async def check_dashboard_delete_access(db: Session, token_payload:dict,project_id:UUID):
  try:
    user_id = UUID(token_payload.get("sub"))
    user_project_role = db.query(UserProjectRoleModel).filter(UserProjectRoleModel.user_id == user_id,UserProjectRoleModel.project_id == project_id).first()
    if not user_project_role:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to this project")
    role_permission = db.query(RolePermissionModel).filter(RolePermissionModel.role_id == user_project_role.role_id, RolePermissionModel.permission_id == "6e073b1d-f56c-4a6e-8a9d-2cb37a4702b4").first()
    if not role_permission:
      raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to delete dashboard")
    else:
      return True
  except Exception as e:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))



async def check_access(
    db: Session,
    token_payload: dict,
    project_id: Optional[UUID] = None,
    permission_key: str = None
):
    try:
        if not token_payload:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token payload")
        
        user_id_str = token_payload.get("sub")
        if not user_id_str:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        try:
            user_id = UUID(user_id_str)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid UUID format in token")

        # First: check if the user exists
        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Allow superusers full access
        if user.is_super:
            return True

        # Special case: CREATE_PROJECT permission doesn't require a project_id
        if permission_key == permission_key.CREATE_PROJECT.value :
            
            user_project_role = db.query(UserProjectRoleModel).filter(
                UserProjectRoleModel.user_id == user_id,
                
            ).all()
            if not user_project_role:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to create projects")
            # Check if any role has the required permission
            for role in user_project_role:
                role_permission = db.query(RolePermissionModel).filter(
                    RolePermissionModel.role_id == role.role_id,
                    RolePermissionModel.permission_id == permission_key.CREATE_PROJECT.value
                ).first()
                if role_permission:
                    return True 
                     # User has the required permission, allow access

            # If we get here, no role had the required permission
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have permission to create projects")
            



            return True
        
        # For all other permissions, we need a project_id
        # if not project_id:
        #     raise HTTPException(
        #         status_code=status.HTTP_400_BAD_REQUEST, 
        #         detail="Project ID is required for this operation"
        #     )

        # Check if user has a role in the project
        user_project_role = db.query(UserProjectRoleModel).filter(
            UserProjectRoleModel.user_id == user_id,
            UserProjectRoleModel.project_id == project_id
        ).first()

        if not user_project_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not have access to this project"
            )

        # Fetch permission ID from permission_key
        permission = db.query(PermissionModel).filter(PermissionModel.type == permission_key).first()
        if not permission:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Permission '{permission_key}' not found"
            )

        # Check if user's role has this permission
        role_permission = db.query(RolePermissionModel).filter(
            RolePermissionModel.role_id == user_project_role.role_id,
            RolePermissionModel.permission_id == permission.id
        ).first()

        if not role_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User does not have '{permission_key}' access"
            )

        return True

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

def require_permission(permission_key: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                # Extract signature of the original function
                sig = inspect.signature(func)
                bound_args = sig.bind_partial(*args, **kwargs)
                
                # Get db and token_payload from arguments
                db = bound_args.arguments.get("db")
                token_payload = bound_args.arguments.get("token_payload")
                
                # project_id is optional and might not be present for CREATE_PROJECT
                project_id = bound_args.arguments.get("project_id")
                
                if not db:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                        detail="Database session not provided"
                    )
                    
                if not token_payload:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED, 
                        detail="Authentication required"
                    )
                
                # For CREATE_PROJECT, we don't need to check project_id
                # so we can call check_access without it
                if permission_key == Permission.CREATE_PROJECT.value:
                    await check_access(db, token_payload, None, permission_key)
                else:
                    # For all other permissions, we need project_id
                    # if not project_id:
                    #     raise HTTPException(
                    #         status_code=status.HTTP_400_BAD_REQUEST, 
                    #         detail="Project ID is required for this operation"
                    #     )
                    await check_access(db, token_payload, project_id, permission_key)
                    
                return await func(*args, **kwargs)
            except Exception as e:
                if isinstance(e, HTTPException):
                    raise e
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Authorization error: {str(e)}"
                )
        
        return wrapper
    return decorator