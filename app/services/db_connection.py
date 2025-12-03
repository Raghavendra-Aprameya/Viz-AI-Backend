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
from urllib.parse import urlparse, quote_plus, parse_qs
import json
from datetime import datetime
from typing import List, Dict, Any

from fastapi import HTTPException, status, Depends, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, text

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


from fastapi import FastAPI, WebSocket, BackgroundTasks, HTTPException
from urllib.parse import urlparse, quote_plus, parse_qs
from uuid import uuid4
import asyncio, json

progress_queues: dict[str, asyncio.Queue] = {}

async def extract_tables_in_background(task_id: str, connection_string: str, db: Session, db_entry_id):
    # ensure the async queue exists and frontend can connect immediately
    queue = progress_queues.setdefault(task_id, asyncio.Queue())

    loop = asyncio.get_running_loop()

    # Run blocking schema extraction in a thread pool
    # get_schema_structure will use loop.call_soon_threadsafe(queue.put_nowait, msg)
    schema_structure = await loop.run_in_executor(
        None,                       # default ThreadPoolExecutor
        get_schema_structure,       # blocking function that now takes (connection_string, queue, loop)
        connection_string,
        queue,
        loop
    )

    # Save schema to DB
    try:
        db_entry = db.query(DatabaseConnectionModel).filter(DatabaseConnectionModel.id == db_entry_id).first()
        db_entry.db_schema = json.dumps(schema_structure)
        db.commit()
    except Exception as e:
        await queue.put({"type": "error", "message": f"Failed saving schema to DB: {e}"})

    # notify completion and sentinel
    await queue.put({"type": "completed", "taskId": task_id})
    await queue.put(None)

    # CLEANUP: remove queue so we don't leak memory (safe - WS should have consumed sentinel)
    progress_queues.pop(task_id, None)


# @require_permission(Permission.ADD_DATASOURCE)
# async def create_database_connection(
#     project_id: UUID,
#     token_payload: dict,
#     data: DBConnectionRequest,
#     db: Session,
# ):
#     """
#     Creates and stores a new database connection for a given project.

#     Args:
#         project_id (UUID): The project to which this DB connection belongs.
#         token_payload (dict): Decoded token payload for permission checks.
#         data (DBConnectionRequest): Input data for creating the DB connection.
#         db (Session): SQLAlchemy DB session.

#     Returns:
#         DBConnectionResponse: Response containing the created DB connection ID.

#     Raises:
#         HTTPException: On invalid DB type or parsing errors.
#     """
#     if data.connection_string:
#         parsed_url = urlparse(data.connection_string)
#         # Normalize parsed components to safe strings
#         raw_username = parsed_url.username or ""
#         raw_password = parsed_url.password or ""
#         raw_host = parsed_url.hostname or ""
#         raw_port = parsed_url.port
#         raw_path = parsed_url.path or ""
#         raw_query = parsed_url.query or ""

#         # Determine final database name: prefer path, else fallback to provided db_name
#         parsed_db_name = raw_path.lstrip("/")
#         final_db_name = parsed_db_name or (data.db_name or "")

#         if not raw_host:
#             raise HTTPException(
#                 status_code=400, detail="Host is required in connection string"
#             )
#         if not final_db_name:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Database name is required (missing in URL and payload)",
#             )

#         # Ensure quote_plus always gets a string
#         encoded_password = quote_plus(str(raw_password))

#         connection_string = (
#             f"{parsed_url.scheme}://{raw_username}:{encoded_password}@"
#             f"{raw_host}{':' + str(raw_port) if raw_port else ''}"
#             f"/{final_db_name}"
#             f"{'?' + raw_query if raw_query else ''}"
#         )

#         db_type = data.db_type
#         schema_structure = get_schema_structure(connection_string)

#         username = raw_username
#         password = str(raw_password)
#         host = raw_host
#         db_name = final_db_name

#     else:
#         db_type = (data.db_type or "").lower()
#         username = data.name or ""
#         password = data.password or ""
#         host = data.host or ""
#         db_name = data.db_name or ""

#         if not host:
#             raise HTTPException(status_code=400, detail="Host is required")
#         if not db_name:
#             raise HTTPException(status_code=400, detail="Database name is required")

#         # Parse host and port from host string (format: "host:port" or just "host")
#         # SQLAlchemy connection strings support port in the format: scheme://user:pass@host:port/db
#         if ":" in host and not host.startswith("["):  # IPv6 addresses start with [
#             # Host already contains port (e.g., "localhost:3306")
#             host_part = host
#         else:
#             # Host doesn't contain port, use default ports
#             if db_type == "postgres":
#                 host_part = f"{host}:5432"
#             elif db_type == "mysql":
#                 host_part = f"{host}:3306"
#             else:
#                 host_part = host

#         if db_type == "postgres":
#             connection_string = (
#                 f"postgresql://{username}:{quote_plus(str(password))}@{host_part}/{db_name}"
#             )
#         elif db_type == "mysql":
#             connection_string = f"mysql+pymysql://{username}:{quote_plus(str(password))}@{host_part}/{db_name}"
#         else:
#             raise HTTPException(status_code=400, detail="Unsupported database type.")

#         schema_structure = get_schema_structure(connection_string)

#     existing = (
#         db.query(DatabaseConnectionModel)
#         .filter(DatabaseConnectionModel.connection_name == data.connection_name)
#         .first()
#     )
#     if existing:
#         raise HTTPException(status_code=400, detail="Connection already exists")

#     db_entry = DatabaseConnectionModel(
#         id=uuid4(),
#         connection_name=data.connection_name,
#         db_connection_string=encrypt_string(connection_string),
#         db_schema=json.dumps(schema_structure),
#         db_username=username,
#         db_password=encrypt_string(password),
#         db_host_link=host,
#         db_name=db_name,
#         project_id=project_id,
#         consent_given=(
#             bool(data.consent_given) if data.consent_given is not None else False
#         ),
#         # db_description=data.db_description,
#         db_type=db_type,
#     )

#     db.add(db_entry)
#     db.flush()

#     table_names = extract_table_names(connection_string)
#     for table_name in table_names:
#         db.add(
#             ConnectionTableNameModel(
#                 table_name=table_name,
#                 connection_id=db_entry.id,
#             )
#         )

#     db.commit()

#     return DBConnectionResponse(db_entry_id=db_entry.id)

async def create_database_connection(
    project_id: UUID,
    token_payload: dict,
    data: DBConnectionRequest,
    db: Session,
    background_tasks: BackgroundTasks
):
    # --- Parse connection string or construct from fields ---
    if data.connection_string:
        # If connection string is provided, use it as-is
        # For Oracle, expect format: oracle+oracledb://username:password@host:port/?service_name=service_name
        parsed_url = urlparse(data.connection_string)
        username = parsed_url.username or ""
        password = parsed_url.password or ""
        host = parsed_url.hostname or ""
        port = parsed_url.port
        
        # Check if it's Oracle
        if parsed_url.scheme and "oracle" in parsed_url.scheme.lower():
            db_type = "oracledb"
            # Extract service_name from query params
            query_params = parse_qs(parsed_url.query)
            service_name = query_params.get("service_name", [None])[0] or parsed_url.path.lstrip("/") or data.db_name or ""
            db_name = service_name
            # Use username/password from URL if available, otherwise from data fields
            username = username or data.username or data.name or ""
            password = password or data.password or ""
            connection_string = data.connection_string
        else:
            # Other database types
            db_name = parsed_url.path.lstrip("/") or data.db_name or ""
            if not host or not db_name:
                raise HTTPException(status_code=400, detail="Host and database name are required")
            # Use username/password from URL if available, otherwise from data fields
            username = username or data.username or data.name or ""
            password = password or data.password or ""
            connection_string = (
                f"{parsed_url.scheme}://{username}:{quote_plus(str(password))}@"
                f"{host}{':' + str(port) if port else ''}/{db_name}"
            )
            db_type = data.db_type
    else:
        # Construct connection string from individual fields
        db_type = (data.db_type or "").lower()
        password = data.password or ""
        host = data.host or ""
        db_name = data.db_name or ""
        
        if db_type == "postgres":
            username = data.username or data.name or ""
            if not all([username, password, host, db_name]):
                raise HTTPException(status_code=400, detail="PostgreSQL requires username (or name), password, host, and database name")
            connection_string = f"postgresql://{username}:{quote_plus(str(password))}@{host}/{db_name}"
        elif db_type == "mysql":
            username = data.username or data.name or ""
            if not all([username, password, host, db_name]):
                raise HTTPException(status_code=400, detail="MySQL requires username (or name), password, host, and database name")
            connection_string = f"mysql+pymysql://{username}:{quote_plus(str(password))}@{host}/{db_name}"
        elif db_type == "oracledb":
            # For Oracle, db_name is actually the service_name
            service_name = db_name
            username = data.username or data.name or ""
            port = "1521"  # Default Oracle port
            if ":" in host:
                # Host contains port
                host, port = host.split(":", 1)
            
            if not all([username, password, host, service_name]):
                raise HTTPException(status_code=400, detail="Oracle requires username (or name), password, host, and service_name (db_name)")
            
            # Build Oracle connection string in the specified format
            connection_string = (
                f"oracle+oracledb://{username}:{quote_plus(str(password))}@{host}:{port}/"
                f"?service_name={service_name}"
            )
        else:
            raise HTTPException(status_code=400, detail="Unsupported database type.")

    # Check for duplicate connection
    existing = db.query(DatabaseConnectionModel).filter(
        DatabaseConnectionModel.connection_name == data.connection_name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Connection already exists")

    # Create DB entry without schema
    db_entry = DatabaseConnectionModel(
        id=uuid4(),
        connection_name=data.connection_name,
        db_connection_string=encrypt_string(connection_string),
        db_schema=None,  # schema will be filled in background
        db_username=username,
        db_password=encrypt_string(password),
        db_host_link=host,
        db_name=db_name,
        project_id=project_id,
        consent_given=bool(data.consent_given) if data.consent_given is not None else False,
        db_type=db_type,
    )
    db.add(db_entry)
    db.commit()
    db.refresh(db_entry)

    # --- Create task ID and start background schema extraction ---
    task_id = str(uuid4())
    background_tasks.add_task(extract_tables_in_background, task_id, connection_string, db, db_entry.id)

    # --- Return immediately ---
    tables_count = len(extract_table_names(connection_string))  
    return {"taskId": task_id, "tablesCount": tables_count}




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


async def get_connection_stats(
    project_id: UUID,
    db: Session,
    token_payload: dict,
):
    """
    Get statistics for database connections in a project.
    
    Args:
        project_id (UUID): The project ID.
        db (Session): The database session.
        token_payload (dict): The token payload.
        
    Returns:
        dict: Statistics about database connections including:
            - total_connections: Total number of connections
            - active_connections: Number of connections with status=True
            - inactive_connections: Number of connections with status=False
            - project_id: The project ID
    """
    from app.models.schema_models import UserProjectRoleModel, UserModel, ProjectModel
    
    user_id = UUID(token_payload.get("sub"))
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token payload"
        )
    
    # Verify project exists
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Verify user has access to this project
    user_role = (
        db.query(UserProjectRoleModel)
        .filter(
            UserProjectRoleModel.user_id == user_id,
            UserProjectRoleModel.project_id == project_id,
        )
        .first()
    )
    
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    
    if not user_role and not user.is_super:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to this project"
        )
    
    # Get all connections for the project
    all_connections = (
        db.query(DatabaseConnectionModel)
        .filter(DatabaseConnectionModel.project_id == project_id)
        .all()
    )
    
    total_connections = len(all_connections)
    active_connections = sum(1 for conn in all_connections if conn.status is True)
    inactive_connections = sum(1 for conn in all_connections if conn.status is False or conn.status is None)
    
    return {
        "total_connections": total_connections,
        "active_connections": active_connections,
        "inactive_connections": inactive_connections,
        "project_id": str(project_id)
    }


async def check_and_update_connections(
    project_id: UUID,
    db: Session,
    token_payload: dict,
) -> Dict[str, Any]:
    """
    Check all database connections for a project and update their status.
    
    This function attempts to connect to each database, updates the status field
    (True if connection succeeds, False if it fails), and updates the last_checked
    timestamp.
    
    Args:
        project_id (UUID): The project ID.
        db (Session): The database session.
        token_payload (dict): The token payload.
        
    Returns:
        dict: Results of connection checks including status updates.
    """
    from app.models.schema_models import UserProjectRoleModel, UserModel, ProjectModel
    
    user_id = UUID(token_payload.get("sub"))
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID not found in token payload"
        )
    
    # Verify project exists
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Verify user has access to this project
    user_role = (
        db.query(UserProjectRoleModel)
        .filter(
            UserProjectRoleModel.user_id == user_id,
            UserProjectRoleModel.project_id == project_id,
        )
        .first()
    )
    
    user = db.query(UserModel).filter(UserModel.id == user_id).first()
    
    if not user_role and not user.is_super:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to this project"
        )
    
    # Get all connections for the project
    connections = (
        db.query(DatabaseConnectionModel)
        .filter(DatabaseConnectionModel.project_id == project_id)
        .all()
    )
    
    if not connections:
        return {
            "message": "No database connections found for this project",
            "project_id": str(project_id),
            "total_checked": 0,
            "successful_connections": 0,
            "failed_connections": 0,
            "results": []
        }
    
    results = []
    successful = 0
    failed = 0
    
    for connection in connections:
        check_result = await _test_single_connection(connection, db)
        results.append(check_result)
        
        if check_result["status"]:
            successful += 1
        else:
            failed += 1
    
    return {
        "message": "Connection check completed",
        "project_id": str(project_id),
        "total_checked": len(connections),
        "successful_connections": successful,
        "failed_connections": failed,
        "results": results
    }


async def _test_single_connection(
    connection: DatabaseConnectionModel,
    db: Session,
) -> Dict[str, Any]:
    """
    Test a single database connection and update its status.
    
    Args:
        connection (DatabaseConnectionModel): The database connection to test.
        db (Session): The database session for updating the record.
        
    Returns:
        dict: Result of the connection test.
    """
    connection_id = str(connection.id)
    connection_name = connection.connection_name
    current_time = datetime.utcnow()
    
    try:
        # Decrypt the connection string
        decrypted_connection_string = decrypt_string(connection.db_connection_string)
        
        # Create a test engine
        test_engine = create_engine(
            decrypted_connection_string,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 10}
        )
        
        # Attempt to connect and execute a simple query
        with test_engine.connect() as conn:
            # Execute a simple query to verify the connection works
            conn.execute(text("SELECT 1"))
        
        # Connection successful - update status to True
        connection.status = True
        connection.last_checked = current_time
        db.commit()
        
        return {
            "connection_id": connection_id,
            "connection_name": connection_name,
            "status": True,
            "last_checked": current_time.isoformat(),
            "error_message": None
        }
        
    except Exception as e:
        # Connection failed - update status to False
        connection.status = False
        connection.last_checked = current_time
        db.commit()
        
        error_msg = str(e)
        # Truncate long error messages
        if len(error_msg) > 200:
            error_msg = error_msg[:200] + "..."
        
        return {
            "connection_id": connection_id,
            "connection_name": connection_name,
            "status": False,
            "last_checked": current_time.isoformat(),
            "error_message": error_msg
        }
