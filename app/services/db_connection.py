from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from uuid import uuid4
import json
from urllib.parse import urlparse, quote_plus

from models import DatabaseConnectionModel, UserProjectRoleModel
from schemas import DBConnectionsRequest, DBConnectionResponse
from security import encrypt_string
from utils import get_schema_structure

async def create_database_connections(data: DBConnectionsRequest, db: Session):
    
    user_id = data.user_id  

    user_project_role = db.query(UserProjectRoleModel).filter_by(
        user_id=user_id,
        project_id=data.project_id,
        role_id=data.role
    ).first()

    if not user_project_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have the required role in this project."
        )

    created_connections = []

    for conn_data in data.connections:
        if conn_data.connection_string:
            parsed_url = urlparse(conn_data.connection_string)
            encoded_password = quote_plus(parsed_url.password) if parsed_url.password else ""
            connection_string = (
                f"{parsed_url.scheme}://{parsed_url.username}:{encoded_password}@"
                f"{parsed_url.hostname}{':' + str(parsed_url.port) if parsed_url.port else ''}"
                f"{parsed_url.path}?{parsed_url.query}"
            )
            schema_structure = get_schema_structure(connection_string, conn_data.db_type)
        
        else:
            db_type = conn_data.db_type.lower()
            username = conn_data.name
            password = quote_plus(conn_data.password)
            host = conn_data.host
            db_name = conn_data.db_name

            if db_type == "postgres":
                connection_string = f"postgresql://{username}:{password}@{host}/{db_name}"
            elif db_type == "mysql":
                connection_string = f"mysql+pymysql://{username}:{password}@{host}/{db_name}"
            else:
                raise HTTPException(status_code=400, detail="Unsupported database type.")

            schema_structure = get_schema_structure(connection_string, db_type)

        # Create database connection entry
        db_entry = DatabaseConnectionModel(
            id=uuid4(),
            db_connection_string=encrypt_string(connection_string),
            db_schema=json.dumps(schema_structure),
            db_username=username,
            db_password=encrypt_string(conn_data.password),
            db_host_link=host,
            db_name=db_name,
            project_id=data.project_id
        )

        db.add(db_entry)
        created_connections.append(DBConnectionResponse(db_entry_id=db_entry.id))

    db.commit()

    return created_connections
