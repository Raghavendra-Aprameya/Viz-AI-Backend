"""
Dashboard Allowed Domains Routes

API routes for managing which app domains are allowed to embed a dashboard.

Routes:
    POST   /api/v1/dashboards/:id/allowed-domains           → attach app domains
    GET    /api/v1/dashboards/:id/allowed-domains           → list attached domains
    DELETE /api/v1/dashboards/:id/allowed-domains/:app_id   → remove a domain
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.utils.token_parser import get_current_user
from app.schemas import (
    SetAllowedDomainsRequest,
    SetAllowedDomainsResponse,
    ListAllowedDomainsResponse,
    RemoveAllowedDomainResponse,
)
from app.services.allowed_domains import (
    set_allowed_domains,
    get_allowed_domains,
    remove_allowed_domain,
)

logger = logging.getLogger(__name__)

allowed_domains_router = APIRouter(
    prefix="/api/v1/dashboards",
    tags=["allowed-domains"],
)


@allowed_domains_router.post(
    "/{dashboard_id}/allowed-domains",
    status_code=status.HTTP_200_OK,
    response_model=SetAllowedDomainsResponse,
)
async def set_allowed_domains_route(
    data: SetAllowedDomainsRequest,
    dashboard_id: UUID = Path(..., description="Dashboard ID"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Attach allowed app domains to a dashboard.
    Replaces any existing allowed domains.
    """
    user_id = UUID(token_payload.get("sub"))
    result = await set_allowed_domains(
        dashboard_id=dashboard_id,
        app_ids=data.app_ids,
        user_id=user_id,
        db=db,
    )
    return result


@allowed_domains_router.get(
    "/{dashboard_id}/allowed-domains",
    status_code=status.HTTP_200_OK,
    response_model=ListAllowedDomainsResponse,
)
async def get_allowed_domains_route(
    dashboard_id: UUID = Path(..., description="Dashboard ID"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    List allowed domains attached to a dashboard.
    """
    result = await get_allowed_domains(
        dashboard_id=dashboard_id,
        db=db,
    )
    return result


@allowed_domains_router.delete(
    "/{dashboard_id}/allowed-domains/{app_id}",
    status_code=status.HTTP_200_OK,
    response_model=RemoveAllowedDomainResponse,
)
async def remove_allowed_domain_route(
    dashboard_id: UUID = Path(..., description="Dashboard ID"),
    app_id: UUID = Path(..., description="App ID to remove"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Remove a specific allowed domain from a dashboard.
    """
    result = await remove_allowed_domain(
        dashboard_id=dashboard_id,
        app_id=app_id,
        db=db,
    )
    return result
