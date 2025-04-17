
from email import message
from pydantic.type_adapter import R
from sqlalchemy.sql.functions import user
from fastapi import Response, Depends, HTTPException, status, Request, Path
from sqlalchemy.orm import Session
from uuid import UUID

# Import schemas and models
from app.schemas import (
    ProjectRequest, CreateDashboardRequest, CreateRoleRequest, 
    UpdateProjectRequest, UpdateDashboardRequest, UpdateRoleRequest,BlackListTableNameRequest
    ,ReadDataRequest
)
from app.core.db import get_db
from app.utils.token_parser import get_current_user
from app.utils.access import require_permission
from app.models.schema_models import (
    ProjectModel, UserProjectRoleModel, RoleModel, DashboardModel, 
    PermissionModel, RolePermissionModel, UserDashboardModel, UserModel,RoleTableNameModel,
    DatabaseConnectionModel
)
from app.utils.constants import Permissions as Permission


@require_permission(Permission.CREATE_PROJECT)
async def create_project(
    project: ProjectRequest, 
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Create a new project and assign the current user as its super user.
    Also assigns the user to the 'ALL role' for that project.
    """
    try:
        user_id_str = token_payload.get("sub")

        if not user_id_str:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

        # Validate UUID
        try:
            user_id = UUID(user_id_str)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid UUID format in token")  
        # Check for duplicate project name
        project_name = db.query(ProjectModel).filter(ProjectModel.name == project.name).first()
        if project_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project name already exists")    
        # Create new project
        new_project = ProjectModel(
            name=project.name,
            description=project.description,
            super_user_id=user_id
        )

        db.add(new_project)
        db.flush()

        # Get role ID of "ALL role"
        role_id = db.query(RoleModel).filter(RoleModel.name == "ALL role").first().id

        # Assign role to user in UserProjectRoleModel
        user_project_role = UserProjectRoleModel(
            user_id=user_id,
            project_id=new_project.id,
            role_id=role_id
        )

        db.add(user_project_role)
        db.commit()
        db.refresh(new_project)
        db.refresh(user_project_role)

        # Return project metadata
        return {
            "message": "Project created successfully", 
            "project": {
                "id": new_project.id,
                "name": new_project.name,
                "description": new_project.description,
                "super_user_id": new_project.super_user_id,
                "created_at": new_project.created_at,
            }
        }

    except Exception as e:
        db.rollback()  # Rollback in case of error
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    

async def get_projects(
    request: Request, 
    response: Response, 
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Get all projects visible to the current user.
    Super users see all projects, others see only their own.
    """
    try:
        user_id_str = token_payload.get("sub")

        if not user_id_str:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
            
        user_id = UUID(user_id_str)
        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        projects = []
        if user.is_super:
            project_list = db.query(ProjectModel).all()
        else:
            # Get all projects where user has a role
            user_project_roles = db.query(UserProjectRoleModel).filter(UserProjectRoleModel.user_id == user_id).all()
            project_ids = [role.project_id for role in user_project_roles]
            project_list = db.query(ProjectModel).filter(ProjectModel.id.in_(project_ids)).all()
            
        # Build projects list with embedded owners
        for project in project_list:
            # Get owners for this project
            owners = db.query(UserProjectRoleModel, UserModel).join(
                UserModel, UserProjectRoleModel.user_id == UserModel.id
            ).filter(
                UserProjectRoleModel.project_id == project.id,
                UserProjectRoleModel.is_owner == True
            ).all()
            
            # Format owners list
            owner_list = []
            for role, user in owners:
                owner_list.append({
                    "id": str(user.id),
                    "username": user.username
                })
            
            # Add project with embedded owners to the result
            projects.append({
                "id": str(project.id),  # Convert UUID to string
                "name": project.name,
                "description": project.description,
                "super_user_id": str(project.super_user_id),  # Convert UUID to string
                "created_at": project.created_at.isoformat(),  # Format datetime as ISO string
                "owners": owner_list
            })

        return {
            "message": "Projects retrieved successfully",   
            "projects": projects
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


async def list_all_roles_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    List all roles associated with a project, including global roles.
    Returns each role's permissions.
    """
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        # Query roles associated with the project or globally available roles
        roles = db.query(RoleModel).filter(
            (RoleModel.project_id == project_id)  | (RoleModel.is_global == True)
        ).all()
        

        roles_list = []

        for role in roles:
            # Get permissions for the role
            permissions = db.query(PermissionModel).join(
                RolePermissionModel,
                PermissionModel.id == RolePermissionModel.permission_id
            ).filter(
                RolePermissionModel.role_id == role.id
            ).all()

            permission_type = [permission.type for permission in permissions]

            roles_list.append({
                "id": role.id,
                "name": role.name,
                "description": role.description or "",
                "permissions": permission_type
            })

        return {
            "message": "Roles retrieved successfully",
            "roles": roles_list
        }

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@require_permission(Permission.CREATE_DASHBOARD)
async def create_dashboard(
    data: CreateDashboardRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
    project_id: UUID = Path(..., description="Project ID to create dashboard for")
):
    """
    Create a new dashboard and assign it to the current user.
    """
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        # Ensure dashboard title is unique
        dashboard_title = db.query(DashboardModel).filter(DashboardModel.title == data.title).first()
        if dashboard_title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dashboard title already exists")

        # Create new dashboard
        new_dashboard = DashboardModel(
            title=data.title,
            description=data.description,
            project_id=project_id,
            created_by=user_id
        )

        db.add(new_dashboard)
        db.flush()

        # Link dashboard to user
        user_dashboard = UserDashboardModel(
            user_id=user_id,
            dashboard_id=new_dashboard.id
        )

        db.add(user_dashboard)
        db.commit()
        db.refresh(new_dashboard)

        return {
            "message": "Dashboard created successfully",
            "dashboard": new_dashboard
        }

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


async def list_all_permissions(
    db: Session = Depends(get_db),
):
    """
    Retrieve all available permissions.
    """
    try:
        permissions = db.query(PermissionModel).all()
        return {
            "message": "Permissions retrieved successfully",
            "permissions": [permission for permission in permissions]
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@require_permission(Permission.CREATE_ROLE)    
async def create_role(
    data: CreateRoleRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
    project_id: UUID = Path(..., description="Project ID to create role for")
):
    """
    Create a new role for a given project and assign it specific permissions.
    """
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

        # Create new role entry
        new_role = RoleModel(
            name=data.name,
            description=data.description,
            project_id=project_id,
        )
        db.add(new_role)
        db.flush()

        # Assign permissions to role
        for permission_id in data.permissions:
            permission_data = db.query(PermissionModel).filter(PermissionModel.id == permission_id).first()
            if not permission_data:
                db.rollback()
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Permission with ID {permission_id} not found")

            role_permission = RolePermissionModel(
                role_id=new_role.id,
                permission_id=permission_id
            )
            db.add(role_permission)

        db.commit()
        db.refresh(new_role)

        return {
            "message": "Role created successfully",
            "role": {
                "id": new_role.id,
                "name": new_role.name,
                "description": new_role.description,
                "project_id": new_role.project_id,
                "permissions": data.permissions
            }
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

async def list_users_all_dashboard(
    project_id: UUID,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    List all dashboards for a given user in a specific project.

    Args:
        project_id (UUID): The ID of the project.
        db (Session): The database session.
        token_payload (dict): The decoded JWT payload containing user details.

    Returns:
        List[dict]: A list of dashboard details such as id, title, description, project_id, and created_by.

    Raises:
        HTTPException: If the user is not authorized, or any database-related error occurs.
    """
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        # Join the tables to get only dashboards that belong to this user AND project
        results = (
            db.query(DashboardModel, UserDashboardModel)
            .join(UserDashboardModel, UserDashboardModel.dashboard_id == DashboardModel.id)
            .filter(
                UserDashboardModel.user_id == user_id,
                DashboardModel.project_id == project_id
            )
            .all()
        )
        
        dashboard_details = []
        for dashboard, user_dashboard in results:
            dashboard_details.append({
                "id": dashboard.id,
                "title": dashboard.title,
                "description": dashboard.description,
                "project_id": dashboard.project_id,
                "created_by": dashboard.created_by,
                "is_favorite": user_dashboard.is_favorite
            })
            
        return dashboard_details
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@require_permission(Permission.DELETE_DASHBOARD)
async def delete_dashboard(
    project_id: UUID,
    dashboard_id: UUID,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Delete a dashboard.

    Args:
        project_id (UUID): The ID of the project.
        dashboard_id (UUID): The ID of the dashboard to delete.
        db (Session): The database session.
        token_payload (dict): The decoded JWT payload containing user details.

    Returns:
        dict: A message indicating the successful deletion of the dashboard.

    Raises:
        HTTPException: If the dashboard is not found or if there are any errors during deletion.
    """
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        dashboard = db.query(DashboardModel).filter(DashboardModel.id == dashboard_id).first()
        if not dashboard:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")
        
        # First delete all user_dashboard associations
        db.query(UserDashboardModel).filter(UserDashboardModel.dashboard_id == dashboard_id).delete()
        
        # Then delete the dashboard
        db.delete(dashboard)
        db.commit()

        return {
            "message": "Dashboard deleted successfully"
        }
    except Exception as e:
        db.rollback()  # Add rollback on error
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@require_permission(Permission.EDIT_PROJECT)        
async def update_project(
    project_id: UUID,
    data: UpdateProjectRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Update a project.

    Args:
        project_id (UUID): The ID of the project to update.
        data (UpdateProjectRequest): The data to update the project with.
        db (Session): The database session.
        token_payload (dict): The decoded JWT payload containing user details.

    Returns:
        dict: A message indicating the successful update of the project, along with updated project data.

    Raises:
        HTTPException: If the project is not found or if there are any errors during the update.
    """
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        
        # Only update fields that are provided in the request
        if data.name is not None:
            project.name = data.name
        if data.description is not None:
            project.description = data.description
            
        db.commit()
        db.refresh(project)

        return {
            "message": "Project updated successfully",
            "project": project
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@require_permission(Permission.DELETE_PROJECT)
async def delete_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Delete a project.

    Args:
        project_id (UUID): The ID of the project to delete.
        db (Session): The database session.
        token_payload (dict): The decoded JWT payload containing user details.

    Returns:
        dict: A message indicating the successful deletion of the project.

    Raises:
        HTTPException: If the project is not found or if there are any errors during deletion.
    """
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        
        db.delete(project)
        db.commit()

        return {
            "message": "Project deleted successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@require_permission(Permission.EDIT_DASHBOARD) 
async def update_dashboard(
    project_id: UUID,
    dashboard_id: UUID,
    data: UpdateDashboardRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
    
):
    """
    Update a dashboard.

    Args:
        project_id (UUID): The ID of the project.
        dashboard_id (UUID): The ID of the dashboard to update.
        data (UpdateDashboardRequest): The data to update the dashboard with.
        db (Session): The database session.
        token_payload (dict): The decoded JWT payload containing user details.

    Returns:
        dict: A message indicating the successful update of the dashboard, along with updated dashboard data.

    Raises:
        HTTPException: If the dashboard is not found or if there are any errors during the update.
    """
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        dashboard = db.query(DashboardModel).filter(DashboardModel.id == dashboard_id,DashboardModel.project_id==project_id).first()
        if not dashboard:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")
        
        if data.title is not None:
            dashboard.title = data.title
        if data.description is not None:
            dashboard.description = data.description
        
        db.commit()
        db.refresh(dashboard)
        
        return {
            "message": "Dashboard updated successfully",
            "dashboard": dashboard
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=str(e)
        ) from e


@require_permission(Permission.EDIT_ROLE)
async def update_role(
    project_id: UUID,
    role_id: UUID,
    data: UpdateRoleRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Update a role.

    Args:
        project_id (UUID): The ID of the project.
        role_id (UUID): The ID of the role to update.
        data (UpdateRoleRequest): The data to update the role with.
        db (Session): The database session.
        token_payload (dict): The decoded JWT payload containing user details.

    Returns:
        dict: A message indicating the successful update of the role, along with updated role data.

    Raises:
        HTTPException: If the role is not found or if there are any errors during the update.
    """
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        role = db.query(RoleModel).filter(RoleModel.id == role_id).first()
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        
        if data.name is not None:
            role.name = data.name
        if data.description is not None:
            role.description = data.description
        
        # Delete existing role permissions
        if data.permissions:
            db.query(RolePermissionModel).filter(RolePermissionModel.role_id == role_id).delete()
            
            # Add new role permissions
            for permission_id in data.permissions:
                permission = db.query(PermissionModel).filter(PermissionModel.id == permission_id).first()
                if not permission:
                    db.rollback()
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Permission with ID {permission_id} not found")
                
                role_permission = RolePermissionModel(
                    role_id=role.id,
                    permission_id=permission_id
                )
                db.add(role_permission)

        db.commit()
        db.refresh(role)
        
        return {
            "message": "Role updated successfully",
            "role": role
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@require_permission(Permission.DELETE_ROLE)  
async def delete_role(
    project_id: UUID,
    role_id: UUID,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Delete a role.

    Args:
        project_id (UUID): The ID of the project.
        role_id (UUID): The ID of the role to delete.
        db (Session): The database session.
        token_payload (dict): The decoded JWT payload containing user details.

    Returns:
        dict: A message indicating the successful deletion of the role.

    Raises:
        HTTPException: If the role is not found or if there are any errors during deletion.
    """
    try:
        user_id = UUID(token_payload.get("sub"))

        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        role = db.query(RoleModel).filter(RoleModel.id == role_id).first()
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        
        # Delete the role - role permissions will be deleted automatically due to cascade
        db.delete(role)
        db.commit()

        return {
            "message": "Role deleted successfully"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


async def get_project_owner_service(
    project_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get the owner of a project.

    Args:
        project_id (UUID): The ID of the project.

    Returns:
        dict: A message indicating the successful retrieval of project owners and a list of owner usernames and user IDs.

    Raises:
        HTTPException: If the project is not found or if there are no owners for the project.
    """
    try:
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

        owners = db.query(UserProjectRoleModel).filter(
            UserProjectRoleModel.project_id == project_id,
            UserProjectRoleModel.is_owner == True
        ).all()
        
        if not owners:
            return {
                "message": "No owners found for this project",
                "owners" : []
            }
        
        owner_list = []
        for owner in owners:
            owner_user = db.query(UserModel).filter(UserModel.id == owner.user_id).first()
            if owner_user:
                owner_list.append({
                    "username": owner_user.username,
                    "user_id": str(owner.user_id)
                })
        
        return {
            "message": "Project owner retrieved successfully",
            "owners": owner_list
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


async def get_dashboard_owner_service(
    dashboard_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Get the owner of a dashboard.

    Args:
        dashboard_id (UUID): The ID of the dashboard.

    Returns:
        dict: A message indicating the successful retrieval of dashboard owners and a list of owner usernames and user IDs.

    Raises:
        HTTPException: If the dashboard is not found or if there are no owners for the dashboard.
    """
    try:
        dashboard = db.query(DashboardModel).filter(DashboardModel.id == dashboard_id).first()
        if not dashboard:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dashboard not found")
        
        owners = db.query(UserDashboardModel).filter(
            UserDashboardModel.dashboard_id == dashboard_id,
            UserDashboardModel.is_owner == True
        ).all()

        if not owners:
            return{
                "message": "No owners found for this dashboard",
                "owners" : []
            }

        owner_list = []
        for owner in owners:
            owner_user = db.query(UserModel).filter(UserModel.id == owner.user_id).first()
            if owner_user:
                owner_list.append({
                    "username": owner_user.username,
                    "user_id": str(owner.user_id)
                })
        return {
            "message": "Dashboard owner retrieved successfully",
            "owners": owner_list
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
async def blacklist_service(project_id, data: BlackListTableNameRequest, db: Session, token_payload: dict):
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        role = db.query(RoleModel).filter(RoleModel.id == data.role_id, RoleModel.project_id==project_id).first()
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        
        # Store all created blacklist entries
        blacklist_entries = []
        
        # Use data.table_name instead of data.table_names
        for table_name in data.table_name:
            already_exists_table_name = db.query(RoleTableNameModel).filter(RoleTableNameModel.table_name_id == table_name, RoleTableNameModel.role_id==data.role_id).first()
            if  already_exists_table_name:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Table name {table_name} already exists in blacklist")
            blacklist = RoleTableNameModel(
                role_id = data.role_id,
                table_name_id = table_name
            )
            db.add(blacklist)
            blacklist_entries.append(blacklist)
        
        db.commit()
        
        # Refresh all blacklist entries if needed
        for entry in blacklist_entries:
            db.refresh(entry)
        
        return {
            "message": "Table names added to blacklist successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

async def update_blacklist_service(project_id, data: BlackListTableNameRequest, db: Session, token_payload: dict):
    try:
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

        role = db.query(RoleModel).filter(RoleModel.id == data.role_id, RoleModel.project_id==project_id).first()
        if not role:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

        # Delete existing blacklist entries
        db.query(RoleTableNameModel).filter(RoleTableNameModel.role_id == data.role_id).delete()
        # Store all created blacklist entries
        blacklist_entries = []
        # Use data.table_name instead of data.table_names
        for table_name in data.table_name:
            blacklist = RoleTableNameModel(
                role_id = data.role_id,
                table_name_id = table_name  
            )
            db.add(blacklist)
            blacklist_entries.append(blacklist)

        db.commit()
        # Refresh all blacklist entries if needed
        for entry in blacklist_entries:
            db.refresh(entry)
        return {
            "message": "Table names updated in blacklist successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

async def read_data_service(data: ReadDataRequest, db: Session, token_payload: dict):
    try:
        # 1. Validate user_id
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing user ID in token payload"
            )
      

       
        database_connection = db.query(DatabaseConnectionModel).filter(
            DatabaseConnectionModel.id == data.connection_id,
            
        ).first()

        if not database_connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Database connection not found or unauthorized"
            )

       
        database_connection.consent_given = not database_connection.consent_given

        db.commit()
        db.refresh(database_connection)

        return {
            "message": "Database connection access permission updated successfully",
            "consent_given": database_connection.consent_given
        }

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format for user ID"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )

    