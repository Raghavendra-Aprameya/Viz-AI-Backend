from pydantic import BaseModel
from typing import Optional,Union,List
from uuid import UUID
from datetime import datetime

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
        
class QueryRequest(BaseModel):
    db_schema: str
    db_type: str
    role: str
    domain: str
    min_date: Optional[Union[datetime, str]] = None
    max_date: Optional[Union[datetime, str]] = None
    api_key: Optional[str] = None


class QueryForExecutor(BaseModel):
    query: str
    explanation: str
    relevance: float
    is_time_based: bool
    chart_type: str


class QueriesForExecutorResponse(BaseModel):
    queries: List[QueryForExecutor]