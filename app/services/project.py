from fastapi import Response, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from datetime import datetime
from uuid import UUID

from app.schemas import ProjectRequest
from app.core.db import get_db
from app.utils.token_parser import parse_token


from app.models.schema_models import ProjectModel 

async def create_project(project: ProjectRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        token_payload = parse_token(request)
        user_id_str = token_payload.get("sub")

        if not user_id_str:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        
        try:
            user_id = UUID(user_id_str)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid UUID format in token")

        new_project = ProjectModel(
            name=project.name,
            description=project.description,
            super_user_id=user_id
        )

        db.add(new_project)
        db.commit()
        db.refresh(new_project)

        # Return dictionary with project data that can be serialized
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))