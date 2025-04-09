from pydantic import BaseModel, EmailStr
from typing import Optional, Any, List
from uuid import UUID
from datetime import datetime
from dataclasses import dataclass, asdict
from app.models.schema_models import UserProjectRoleModel, UserModel, UserDashboardModel
class DBConnectionRequest(BaseModel):
    connection_name: str  
    connection_string: Optional[str] = None
    domain: Optional[str] = None
    db_type: Optional[str] = None
    api_key: Optional[str] = None
    password: Optional[str] = None
    host: Optional[str] = None
    db_name: Optional[str] = None 
    user_id: UUID
    project_id: UUID
    role: UUID
    name: Optional[str] = None         # 👈 Needed


class DBConnectionResponse(BaseModel):
    db_entry_id: UUID


class DBConnectionListResponse(BaseModel):
    message: str
    connections: List[dict]

    class Config:
        from_attributes = True


class UserRequest(BaseModel):
    username: str
    password: str
    email: str
    


class LoginData(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: UUID
    username: str
    email: str

    class Config:
        from_attributes = True  # This allows Pydantic to work with SQLAlchemy models

class ProjectRequest(BaseModel):
    name: str  
    description: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True



class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    super_user_id: UUID
    created_at: datetime
    
    
    class Config:
        from_attributes = True  # For Pydantic v2, this replaces orm_mode

class ConnectionRequest(BaseModel):
    project_id: UUID

class ProjectsResponse(BaseModel):
    message: str
    projects: List[ProjectResponse]

class UserProjectRole(BaseModel):
    id: UUID
    user_id: UUID
    project_id: UUID
    role_id: UUID

    class Config:
        from_attributes = True

class CreateUserProjectRequest(BaseModel):
    username: str
    email: str
    password: str
    role_id: UUID
    
class CreateUserProjectResponse(BaseModel):
    message: str
    user_project: UserProjectRole
    user: UserResponse

class UserProjectDetails(BaseModel):
    id: UUID
    user_id: UUID  
    project_id: UUID
    role_id: UUID
    username: str
    password: str
    email: str
    created_at: str

    class Config:
        from_attributes = True

class ListAllUsersProjectResponse(BaseModel):
    message: str
    users: List[UserProjectDetails]

    class Config:
        from_attributes = True

class RoleResponse(BaseModel):
    id: UUID
    name: str
    description: str

class ListAllRolesProjectResponse(BaseModel):
    message: str
    roles: List[RoleResponse]

    class Config:
        from_attributes = True

class CreateDashboardRequest(BaseModel):
    title: str
    description: Optional[str] = None
    

class DashboardResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    project_id: UUID
    created_by: UUID
    

class CreateDashboardResponse(BaseModel):
    message: str
    dashboard: DashboardResponse

class PermissionResponse(BaseModel):
    id: UUID
    type: str

class ListAllPermissionsResponse(BaseModel):
    message: str
    permissions: List[PermissionResponse]

    class Config:
        from_attributes = True

class PermissionAssign(BaseModel):
    permission_id: UUID


class CreateRoleRequest(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: List[UUID]


class RolePermissionResponse(BaseModel):
    id: UUID
    name: str
    description: str
    project_id: UUID
    permissions: List[UUID]

class CreateRoleResponse(BaseModel):
    message: str
    role: RolePermissionResponse

class AddUserDashboardRequest(BaseModel):
    user_id: UUID
    dashboard_id: UUID

class UserDashboardResponse(BaseModel):
    id: UUID
    user_id: UUID
    dashboard_id: UUID
    can_read: bool
    can_write: bool
    can_delete: bool

    class Config:
        from_attributes = True

class AddUserDashboardResponse(BaseModel):
    message: str
    user_dashboard: UserDashboardResponse

class UserDashboardReponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    project_id: UUID
    created_by: UUID

    class Config:
        from_attributes = True
    

class ListAllUsersDashboardResponse(BaseModel):
    message: str
    dashboards: List[UserDashboardReponse]

    class Config:
        from_attributes = True



class DeleteDashboardResponse(BaseModel):
    message: str

class CreateProjectResponse(BaseModel):
    message: str
    project: dict

    class Config:
        from_attributes = True

class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class UpdateDashboardRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
