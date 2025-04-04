from pydantic import BaseModel, EmailStr
from typing import Optional, Any, List
from uuid import UUID
from datetime import datetime
from dataclasses import dataclass, asdict

class DBConnectionRequest(BaseModel):
    connection_string: Optional[str] = None
    domain: Optional[str] = None
    db_type: Optional[str] = None
    api_key: Optional[str] = None
    password: Optional[str] = None
    host: Optional[str] = None
    db_name: Optional[str] = None
    name: Optional[str] = None  # Username

class DBConnectionsRequest(BaseModel):
    user_id: UUID  # User ID comes from frontend
    project_id: UUID
    role: UUID   
    connections: List[DBConnectionRequest]

class DBConnectionResponse(BaseModel):
    db_entry_id: UUID

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