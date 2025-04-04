from fastapi import APIRouter, status, Response, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas import ProjectRequest
from app.services.project import create_project
from app.utils.token_parser import parse_token

backend_router = APIRouter(prefix="/api/v1/backend", tags=["backend"])

@backend_router.post("/create-project", status_code=status.HTTP_201_CREATED, dependencies=[Depends(parse_token)])
async def create_project_route(project: ProjectRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    return await create_project(project, request, response, db)