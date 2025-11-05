"""
Module for managing database connections in the project.

This module contains API routes for creating, retrieving, updating, and deleting
database connections for specific projects. It interacts with the database to store
and retrieve connection details securely, including connection strings, usernames,
passwords, and schemas. Encryption is used to protect sensitive data like passwords
and connection strings.

Key Features:
- Create a new database connection for a project.
- Retrieve all database connections associated with a project.
- Update an existing database connection.
- Delete a database connection.

Security:
- Sensitive data such as passwords and connection strings are encrypted before storage.
- Only authorized users with the appropriate permissions (ADD_DATASOURCE, VIEW_DATASOURCE,
  EDIT_DATASOURCE, DELETE_DATASOURCE) can access these operations.

Modules and Functions:
- create_database_connection: Creates and stores a new database connection for a project.
- get_connections: Retrieves all database connections associated with a specific project.
- update_db_connection: Updates an existing database connection.
- delete_db_connection: Deletes a database connection by its ID.

Exception Handling:
- HTTPExceptions are raised in case of errors, such as unsupported
  database types or invalid connections.
- If a user attempts to access a connection they don't have permission for, an exception is raised.

Module Dependencies:
- FastAPI: Provides the web framework for handling API routes.
- SQLAlchemy: Interacts with the database to store and retrieve connection data.
- app.utils.crypt: Provides encryption and decryption utilities for sensitive data.
- app.utils.schema_structure: Extracts schema structure from the database.
- app.utils.extract_table_name: Extracts table names from the database.
- app.utils.token_parser: Provides token-based user authentication and permission checks.
- app.utils.access: Manages user permissions and access control.

This module ensures that database connections are managed securely, and provides an interface for
users with the correct permissions to interact with these connections.
"""

from uuid import UUID, uuid4
from urllib.parse import urlparse, quote_plus
import json

from fastapi import HTTPException, status, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.schema_models import ConnectionTableNameModel, DatabaseConnectionModel
from app.schemas import (
    DBConnectionRequest,
    DBConnectionResponse,
    UpdateDBConnectionRequest,
)
from app.utils.crypt import encrypt_string, decrypt_string
from app.utils.schema_structure import get_schema_structure
from app.utils.extract_table_name import extract_table_names
from app.utils.token_parser import get_current_user
from app.utils.constants import Permissions as Permission
from app.utils.access import require_permission


@require_permission(Permission.ADD_DATASOURCE)
async def create_database_connection(
    project_id: UUID,
    token_payload: dict,
    data: DBConnectionRequest,
    db: Session,
):
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
    if data.connection_string:
        parsed_url = urlparse(data.connection_string)
        # Normalize parsed components to safe strings
        raw_username = parsed_url.username or ""
        raw_password = parsed_url.password or ""
        raw_host = parsed_url.hostname or ""
        raw_port = parsed_url.port
        raw_path = parsed_url.path or ""
        raw_query = parsed_url.query or ""

        # Determine final database name: prefer path, else fallback to provided db_name
        parsed_db_name = raw_path.lstrip("/")
        final_db_name = parsed_db_name or (data.db_name or "")

        if not raw_host:
            raise HTTPException(
                status_code=400, detail="Host is required in connection string"
            )
        if not final_db_name:
            raise HTTPException(
                status_code=400,
                detail="Database name is required (missing in URL and payload)",
            )

        # Ensure quote_plus always gets a string
        encoded_password = quote_plus(str(raw_password))

        connection_string = (
            f"{parsed_url.scheme}://{raw_username}:{encoded_password}@"
            f"{raw_host}{':' + str(raw_port) if raw_port else ''}"
            f"/{final_db_name}"
            f"{'?' + raw_query if raw_query else ''}"
        )

        db_type = data.db_type
        schema_structure = get_schema_structure(connection_string)

        username = raw_username
        password = str(raw_password)
        host = raw_host
        db_name = final_db_name

    else:
        db_type = (data.db_type or "").lower()
        username = data.name or ""
        password = data.password or ""
        host = data.host or ""
        db_name = data.db_name or ""

        if not host:
            raise HTTPException(status_code=400, detail="Host is required")
        if not db_name:
            raise HTTPException(status_code=400, detail="Database name is required")

        if db_type == "postgres":
            connection_string = (
                f"postgresql://{username}:{quote_plus(str(password))}@{host}/{db_name}"
            )
        elif db_type == "mysql":
            connection_string = f"mysql+pymysql://{username}:{quote_plus(str(password))}@{host}/{db_name}"
        else:
            raise HTTPException(status_code=400, detail="Unsupported database type.")

        schema_structure = get_schema_structure(connection_string)

    existing = (
        db.query(DatabaseConnectionModel)
        .filter(DatabaseConnectionModel.connection_name == data.connection_name)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Connection already exists")

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
        consent_given=(
            bool(data.consent_given) if data.consent_given is not None else False
        ),
        # db_description=data.db_description,
        db_type=db_type,
    )

    db.add(db_entry)
    db.flush()

    table_names = extract_table_names(connection_string)
    for table_name in table_names:
        db.add(
            ConnectionTableNameModel(
                table_name=table_name,
                connection_id=db_entry.id,
            )
        )

    db.commit()

    return DBConnectionResponse(db_entry_id=db_entry.id)


@require_permission(Permission.VIEW_DATASOURCE)
async def get_connections(
    project_id: UUID,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Retrieves all database connections for a project.

    Args:
        project_id (UUID): Project identifier.
        request (Request): FastAPI request object.
        response (Response): FastAPI response object.
        db (Session): SQLAlchemy DB session.
        token_payload (dict): Authenticated user's token payload.

    Returns:
        dict: List of decrypted database connections.
    """
    try:
        user_id_str = token_payload.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        UUID(user_id_str)  # Validate UUID

        connections = (
            db.query(DatabaseConnectionModel)
            .filter(DatabaseConnectionModel.project_id == project_id)
            .all()
        )

        connections_list = []
        for conn in connections:
            if conn.db_type == "spreadsheet":
                decrypted_password = conn.db_password
                decrypted_connection_string = conn.db_connection_string
            else:
                decrypted_password = decrypt_string(conn.db_password)
                decrypted_connection_string = decrypt_string(conn.db_connection_string)

            connections_list.append(
                {
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
                    "consent_given": conn.consent_given,
                }
            )

        return {
            "message": "Connections retrieved successfully",
            "connections": connections_list,
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e


@require_permission(Permission.EDIT_DATASOURCE)
async def update_db_connection(
    connection_id: UUID,
    data: UpdateDBConnectionRequest,
    db: Session,
    token_payload: dict,
):
    """
    Updates an existing database connection.

    Args:
        connection_id (UUID): ID of the DB connection to update.
        data (UpdateDBConnectionRequest): Updated connection details.
        db (Session): SQLAlchemy DB session.

    Returns:
        dict: Success message on update.

    Raises:
        HTTPException: If connection is not found.
    """
    db_connection = (
        db.query(DatabaseConnectionModel)
        .filter(DatabaseConnectionModel.id == connection_id)
        .first()
    )
    if not db_connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Database connection not found",
        )

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
async def delete_db_connection(
    connection_id: UUID,
    db: Session,
    token_payload: dict,
):
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
    db_connection = (
        db.query(DatabaseConnectionModel)
        .filter(DatabaseConnectionModel.id == connection_id)
        .first()
    )
    if not db_connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Database connection not found",
        )

    db.delete(db_connection)
    db.commit()

    return {"message": "Database connection deleted successfully"}
