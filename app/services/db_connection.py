from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from uuid import uuid4
import json
from urllib.parse import urlparse, quote_plus

from app.models.schema_models import DatabaseConnectionModel, UserProjectRoleModel
from app.schemas import DBConnectionRequest, DBConnectionResponse
from app.utils.crypt import encrypt_string
from app.utils.schema_structure import get_schema_structure

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
