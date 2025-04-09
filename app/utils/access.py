from app.models.schema_models import UserProjectRoleModel,UserDashboardModel,UserChartModel,PermissionModel,RolePermissionModel
from app.utils.token_parser import get_current_user
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
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
  
# def check_project_create_access(db: Session):
#   try:
#     user_id = UUID(get_current_user(db).get("sub"))
#     user_project_role = db.query(UserProjectRoleModel).filter(UserProjectRoleModel.user_id == user_id, UserProjectRoleModel.project_id == project_id).first()
#     if not user_project_role:
#       raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to this project")
#     role_permission = db.query(RolePermissionModel).filter(RolePermissionModel.role_id == user_project_role.role_id, RolePermissionModel.permission_id == "8e1c6f1e-7c99-4f28-bd2e-c7b79d6122c1").first()
#     if not role_permission:
#       raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User does not have access to create project")
#     else:
#       return True
#   except Exception as e:
#     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

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
