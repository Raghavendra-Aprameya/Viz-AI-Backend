from multiprocessing import connection
from sqlalchemy.orm import Session
from fastapi import HTTPException, status, Depends, Request, Response
from uuid import uuid4, UUID

import json
from urllib.parse import urlparse, quote_plus

from app.core.db import get_db
from app.models.schema_models import ConnectionTableNameModel, DatabaseConnectionModel
from app.schemas import DBConnectionRequest, DBConnectionResponse, UpdateDBConnectionRequest
from app.utils.crypt import encrypt_string, decrypt_string
from app.utils.schema_structure import get_schema_structure
from app.utils.extract_table_name import extract_table_names
from app.utils.token_parser import  get_current_user
from app.utils.constants import Permissions as Permission
from app.utils.access import require_permission

@require_permission(Permission.ADD_DATASOURCE)
async def create_database_connection(project_id: UUID, token_payload: dict, data: DBConnectionRequest, db: Session):
    """
    Creates and stores a new database connection for a given project.

    Args:
        project_id (UUID): The project to which this DB connection belongs.
        token_payload (dict): Decoded token payload for permission checks.
        data (DBConnectionRequest): Input data for creating the DB connection.
        db (Session): SQLAlchemy DB session.

    Returns:
        DBConnectionResponse: Response containing the created DB connection ID.

    Raises:
        HTTPException: On invalid DB type or parsing errors.
    """
    # If a raw connection string is provided, parse and extract details
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

        # Extract individual components
        username = parsed_url.username
        password = parsed_url.password
        host = parsed_url.hostname
        db_name = parsed_url.path.lstrip("/")

    else:
        # Manually build the connection string based on DB type
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

    connections = db.query(DatabaseConnectionModel).filter(
            DatabaseConnectionModel.connection_name == data.connection_name).first()
    if connections:
            raise HTTPException(status_code=400, detail="Connection already exists")
    
    # Save encrypted connection and password to the database
    db_entry = DatabaseConnectionModel(
        id=uuid4(),
        connection_name=data.connection_name,
        db_connection_string=encrypt_string(connection_string),
        db_schema=json.dumps(schema_structure),
        db_username=username,
        db_password=encrypt_string(password),
        db_host_link=host,
        db_name=db_name,
        project_id=project_id,
        grant_access= data.grant_access,
    )

    db.add(db_entry)
    db.flush()  # Flush to get the id of db_entry
    
    table_names = extract_table_names(connection_string)
    for table_name in table_names:
        # Create a new ConnectionTableNameModel instance
        new_table_name = ConnectionTableNameModel(
            table_name=table_name,
            connection_id=db_entry.id
        )
        db.add(new_table_name)

    db.commit()
    
    return DBConnectionResponse(db_entry_id=db_entry.id)


@require_permission(Permission.VIEW_DATASOURCE)
async def get_connections(
    project_id: UUID, 
    request: Request, 
    response: Response, 
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    """
    Retrieves all database connections for the specified project.

    Args:
        project_id (UUID): Project whose DB connections are to be fetched.
        request (Request): FastAPI request object.
        response (Response): FastAPI response object.
        db (Session): SQLAlchemy DB session.
        token_payload (dict): Parsed token payload.

    Returns:
        dict: A list of decrypted and structured DB connections.
    """
    try:
        user_id_str = token_payload.get("sub")
        if not user_id_str:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        try:
            user_id = UUID(user_id_str)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid UUID format in token")

        # Query database connections for the project
        connections = db.query(DatabaseConnectionModel).filter(
            DatabaseConnectionModel.project_id == project_id
        ).all()

        # Format and decrypt connections
        connections_list = []
        for conn in connections:
            decrypted_password = decrypt_string(conn.db_password)
            decrypted_connection_string = decrypt_string(conn.db_connection_string)

            conn_dict = {
                "id": str(conn.id),
                "project_id": str(conn.project_id),
                "db_connection_string": decrypted_connection_string,
                "db_schema": conn.db_schema,
                "db_username": conn.db_username,
                "db_password": decrypted_password,
                "db_host_link": conn.db_host_link,
                "db_name": conn.db_name,
                "db_type": conn.db_type,
                "name": conn.connection_name,
                "consent_given": conn.consent_given
            }
            connections_list.append(conn_dict)

        return {
            "message": "Connections retrieved successfully",
            "connections": connections_list
        }

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@require_permission(Permission.EDIT_DATASOURCE)
async def update_db_connection(connection_id: UUID, data: UpdateDBConnectionRequest, db: Session):
    """
    Updates an existing database connection with new information.

    Args:
        connection_id (UUID): ID of the DB connection to update.
        data (UpdateDBConnectionRequest): Updated connection details.
        db (Session): SQLAlchemy DB session.

    Returns:
        dict: Success message on update.

    Raises:
        HTTPException: If connection is not found.
    """
    db_connection = db.query(DatabaseConnectionModel).filter(DatabaseConnectionModel.id == connection_id).first()
    if not db_connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database connection not found")

    # Update only the provided fields
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

@require_permission(Permission.DELETE_DATASOURCE)
async def delete_db_connection(connection_id: UUID, db: Session,token_payload: dict):
    ""
    """
    Deletes a database connection by ID.

    Args:
        connection_id (UUID): ID of the DB connection to delete.
        db (Session): SQLAlchemy DB session.

    Returns:
        dict: Success message on deletion.

    Raises:
        HTTPException: If the connection is not found.
    """
    db_connection = db.query(DatabaseConnectionModel).filter(DatabaseConnectionModel.id == connection_id).first()
    if not db_connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database connection not found")

    db.delete(db_connection)
    db.commit()

    return {"message": "Database connection deleted successfully"}
