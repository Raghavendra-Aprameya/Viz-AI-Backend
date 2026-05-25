"""
App Registration Routes

API routes for managing app registrations (external applications
that embed dashboards via domain-locked iframe links).

Routes:
    POST   /api/v1/apps           → create app record
    GET    /api/v1/apps           → list apps for current user
    DELETE /api/v1/apps/:app_id   → soft delete (is_active = false)
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.utils.token_parser import get_current_user
from app.schemas import (
    CreateAppRequest,
    CreateAppResponse,
    ListAppsResponse,
    DeleteAppResponse,
)
from app.services.app_service import (
    create_app,
    list_apps,
    delete_app,
)

logger = logging.getLogger(__name__)

apps_router = APIRouter(prefix="/api/v1/apps", tags=["apps"])


@apps_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateAppResponse,
)
async def create_app_route(
    data: CreateAppRequest,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Create a new app registration with company name and domain URL.
    Domain URL is normalized to a bare hostname.
    """
    user_id = UUID(token_payload.get("sub"))
    result = await create_app(
        user_id=user_id,
        company_name=data.company_name,
        domain_url=data.domain_url,
        db=db,
    )
    return result


@apps_router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=ListAppsResponse,
)
async def list_apps_route(
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    List all active apps registered by the current user.
    """
    user_id = UUID(token_payload.get("sub"))
    result = await list_apps(user_id=user_id, db=db)
    return result


@apps_router.delete(
    "/{app_id}",
    status_code=status.HTTP_200_OK,
    response_model=DeleteAppResponse,
)
async def delete_app_route(
    app_id: UUID = Path(..., description="App ID to soft-delete"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Soft-delete an app (sets is_active = false).
    Does not hard delete — preserves audit trail.
    """
    user_id = UUID(token_payload.get("sub"))
    result = await delete_app(
        app_id=app_id,
        user_id=user_id,
        db=db,
    )
    return result
