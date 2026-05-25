"""
Allowed Domains Service

Handles attaching, listing, and removing allowed app domains
on dashboards. The allowed domains determine which external
origins can load the embedded dashboard.
"""

import logging
import time
from typing import List
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.schema_models import (
    AppModel,
    DashboardAllowedDomainModel,
    DashboardModel,
)

logger = logging.getLogger(__name__)


async def set_allowed_domains(
    dashboard_id: UUID,
    app_ids: List[UUID],
    user_id: UUID,
    db: Session,
) -> dict:
    """
    Set the allowed domains for a dashboard by attaching apps.
    Replaces any existing allowed domains.

    STEP 5: Allowed domains set for dashboard

    Args:
        dashboard_id: UUID of the dashboard
        app_ids: List of app UUIDs to attach
        user_id: UUID of the authenticated user
        db: SQLAlchemy session

    Returns:
        dict with allowed domain details
    """
    start_time = time.time()

    # Verify dashboard exists
    dashboard = db.query(DashboardModel).filter(
        DashboardModel.id == dashboard_id
    ).first()

    if not dashboard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard not found",
        )

    # Verify all apps exist and belong to the user
    apps = (
        db.query(AppModel)
        .filter(
            and_(
                AppModel.app_id.in_(app_ids),
                AppModel.created_by == user_id,
                AppModel.is_active == True,
            )
        )
        .all()
    )

    found_ids = {app.app_id for app in apps}
    missing_ids = set(app_ids) - found_ids
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Some apps not found or not owned by you: {[str(mid)[:8] for mid in missing_ids]}",
        )

    # Remove existing allowed domains for this dashboard
    db.query(DashboardAllowedDomainModel).filter(
        DashboardAllowedDomainModel.dashboard_id == dashboard_id
    ).delete()

    # Add new allowed domains
    new_entries = []
    for app in apps:
        entry = DashboardAllowedDomainModel(
            dashboard_id=dashboard_id,
            app_id=app.app_id,
        )
        db.add(entry)
        new_entries.append(entry)

    db.commit()

    # Refresh to get added_at timestamps
    for entry in new_entries:
        db.refresh(entry)

    domain_list = [app.domain_url for app in apps]
    duration_ms = int((time.time() - start_time) * 1000)

    # [STEP 5] Allowed domains set
    logger.info(
        f"[EMBED][STEP 5] Allowed domains set for dashboard {str(dashboard_id)[:8]}... "
        f"— domains: {domain_list} — duration: {duration_ms}ms"
    )

    return {
        "message": f"{len(apps)} allowed domain(s) set for dashboard",
        "dashboard_id": dashboard_id,
        "allowed_domains": [
            {
                "app_id": app.app_id,
                "company_name": app.company_name,
                "domain_url": app.domain_url,
                "added_at": entry.added_at,
            }
            for app, entry in zip(apps, new_entries)
        ],
    }


async def get_allowed_domains(
    dashboard_id: UUID,
    db: Session,
) -> dict:
    """
    List allowed domains for a dashboard.

    Args:
        dashboard_id: UUID of the dashboard
        db: SQLAlchemy session

    Returns:
        dict with allowed domain details
    """
    entries = (
        db.query(DashboardAllowedDomainModel)
        .filter(DashboardAllowedDomainModel.dashboard_id == dashboard_id)
        .all()
    )

    allowed_domains = []
    for entry in entries:
        app = db.query(AppModel).filter(
            and_(
                AppModel.app_id == entry.app_id,
                AppModel.is_active == True,
            )
        ).first()
        if app:
            allowed_domains.append({
                "app_id": app.app_id,
                "company_name": app.company_name,
                "domain_url": app.domain_url,
                "added_at": entry.added_at,
            })

    return {
        "message": f"{len(allowed_domains)} allowed domain(s) found",
        "dashboard_id": dashboard_id,
        "allowed_domains": allowed_domains,
    }


async def remove_allowed_domain(
    dashboard_id: UUID,
    app_id: UUID,
    db: Session,
) -> dict:
    """
    Remove a specific allowed domain from a dashboard.

    Args:
        dashboard_id: UUID of the dashboard
        app_id: UUID of the app to remove
        db: SQLAlchemy session

    Returns:
        dict with removal result
    """
    start_time = time.time()

    entry = db.query(DashboardAllowedDomainModel).filter(
        and_(
            DashboardAllowedDomainModel.dashboard_id == dashboard_id,
            DashboardAllowedDomainModel.app_id == app_id,
        )
    ).first()

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allowed domain not found for this dashboard",
        )

    db.delete(entry)
    db.commit()

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        f"[EMBED] Allowed domain removed — dashboard: {str(dashboard_id)[:8]}..., "
        f"app: {str(app_id)[:8]}... — duration: {duration_ms}ms"
    )

    return {
        "message": "Allowed domain removed successfully",
        "dashboard_id": dashboard_id,
        "app_id": app_id,
    }


def get_allowed_domains_list(
    dashboard_id: UUID,
    db: Session,
) -> List[str]:
    """
    Get the list of allowed domain hostnames for a dashboard.
    Used internally by the embed service for domain-lock enforcement.

    Args:
        dashboard_id: UUID of the dashboard
        db: SQLAlchemy session

    Returns:
        List of bare hostnames
    """
    entries = (
        db.query(DashboardAllowedDomainModel)
        .filter(DashboardAllowedDomainModel.dashboard_id == dashboard_id)
        .all()
    )

    domains = []
    for entry in entries:
        app = db.query(AppModel).filter(
            and_(
                AppModel.app_id == entry.app_id,
                AppModel.is_active == True,
            )
        ).first()
        if app:
            domains.append(app.domain_url)

    return domains
