from sqlalchemy.orm import Session
from fastapi import HTTPException, status, Depends, Request, Response
from uuid import uuid4, UUID

import json
from urllib.parse import urlparse, quote_plus

from app.core.db import get_db
from app.models.schema_models import DatabaseConnectionModel, UserProjectRoleModel
from app.schemas import DBConnectionRequest, DBConnectionResponse, UpdateDBConnectionRequest
from app.utils.crypt import encrypt_string, decrypt_string
from app.utils.schema_structure import get_schema_structure
from app.utils.token_parser import parse_token, get_current_user

async def create_database_connection(data: DBConnectionRequest, db: Session):
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

    if data.connection_string:
        parsed_url = urlparse(data.connection_string)
        encoded_password = quote_plus(parsed_url.password) if parsed_url.password else ""
        connection_string = (
            f"{parsed_url.scheme}://{parsed_url.username}:{encoded_password}@"
            f"{parsed_url.hostname}{':' + str(parsed_url.port) if parsed_url.port else ''}"
            f"{parsed_url.path}?{parsed_url.query}"
        )
        db_type = data.db_type
        schema_structure = get_schema_structure(connection_string, db_type)
        username = parsed_url.username
        password = parsed_url.password
        host = parsed_url.hostname
        db_name = parsed_url.path.lstrip("/")
    else:
        db_type = data.db_type.lower()
        username = data.name
        password = data.password
        host = data.host
        db_name = data.db_name

        if db_type == "postgres":
            connection_string = f"postgresql://{username}:{quote_plus(password)}@{host}/{db_name}"
        elif db_type == "mysql":
            connection_string = f"mysql+pymysql://{username}:{quote_plus(password)}@{host}/{db_name}"
        else:
            raise HTTPException(status_code=400, detail="Unsupported database type.")

        schema_structure = get_schema_structure(connection_string, db_type)

    db_entry = DatabaseConnectionModel(
        id=uuid4(),
        connection_name=data.connection_name,  # 👈 New field
        db_connection_string=encrypt_string(connection_string),
        db_schema=json.dumps(schema_structure),
        db_username=username,
        db_password=encrypt_string(password),
        db_host_link=host,
        db_name=db_name,
        project_id=data.project_id
    )

    db.add(db_entry)
    db.commit()
    db.refresh(db_entry)

    return DBConnectionResponse(db_entry_id=db_entry.id)

async def get_connections(
    project_id: UUID, 
    request: Request, 
    response: Response, 
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    try:
        user_id_str = token_payload.get("sub")

        if not user_id_str:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        try:
            user_id = UUID(user_id_str)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid UUID format in token")
        
        # Query all connections for the project
        connections = db.query(DatabaseConnectionModel).filter(
            DatabaseConnectionModel.project_id == project_id
        ).all()
        
        # Convert SQLAlchemy models to dictionaries
        connections_list = []
        for conn in connections:

            # Decrypt the password
            decrypted_password = decrypt_string(conn.db_password)
            # Decrypt the connection string
            decrypted_connection_string = decrypt_string(conn.db_connection_string)
            # Create a new dictionary with the decrypted password and connection string 
            conn_dict = {
                "id": str(conn.id),
                "project_id": str(conn.project_id),
                "db_connection_string": decrypted_connection_string,
                "db_schema": conn.db_schema,
                "db_username": conn.db_username,
                "db_password": decrypted_password,
                "db_host_link": conn.db_host_link,
                "db_name": conn.db_name,
                "db_type":conn.db_type,
                "name":conn.connection_name
            }
            connections_list.append(conn_dict)


        return {
            "message": "Connections retrieved successfully",
            "connections": connections_list
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
async def update_db_connection(connection_id: UUID, data: UpdateDBConnectionRequest, db: Session):
    db_connection = db.query(DatabaseConnectionModel).filter(DatabaseConnectionModel.id == connection_id).first()
    if not db_connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database connection not found")
    
    if data.connection_name:
        db_connection.connection_name = data.connection_name
    if data.db_connection_string:
        db_connection.db_connection_string = data.db_connection_string
    if data.db_schema:
        db_connection.db_schema = data.db_schema
    if data.db_username:
        db_connection.db_username = data.db_username
    if data.db_password:
        db_connection.db_password = data.db_password
    if data.db_host_link:
        db_connection.db_host_link = data.db_host_link
    if data.db_name:
        db_connection.db_name = data.db_name
    if data.db_type:
        db_connection.db_type = data.db_type
       
    db.commit()
    db.refresh(db_connection)
    return {"message": "Database connection updated successfully"}

async def delete_db_connection(connection_id: UUID, db: Session):
    db_connection = db.query(DatabaseConnectionModel).filter(DatabaseConnectionModel.id == connection_id).first()
    if not db_connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database connection not found")
    db.delete(db_connection)
    db.commit()
    return {"message": "Database connection deleted successfully"}