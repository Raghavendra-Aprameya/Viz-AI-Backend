"""
App Service

Handles CRUD operations for app registrations (external applications
that can embed dashboards). Includes domain URL normalization.
"""

import logging
import re
import time
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.schema_models import AppModel

logger = logging.getLogger(__name__)


def normalize_domain(raw_domain: str) -> str:
    """
    Normalize a domain URL to a bare hostname.
    
    Strips protocol (http://, https://), 'www.' prefix, trailing slashes,
    paths, ports, and query strings.
    
    Examples:
        'https://www.fedex.com/'      → 'fedex.com'
        'http://dhl.com/tracking'     → 'dhl.com'
        'fedex.com:8080'              → 'fedex.com'
        'WWW.Example.COM'             → 'example.com'
    """
    domain = raw_domain.strip().lower()
    
    # Strip protocol
    domain = re.sub(r'^https?://', '', domain)
    
    # Strip www.
    domain = re.sub(r'^www\.', '', domain)
    
    # Strip paths, query strings, fragments
    domain = domain.split('/')[0]
    domain = domain.split('?')[0]
    domain = domain.split('#')[0]
    
    # Strip port
    domain = domain.split(':')[0]
    
    # Strip trailing dots
    domain = domain.rstrip('.')
    
    # Treat localhost and 127.0.0.1 as equivalent
    if domain in ("localhost", "127.0.0.1"):
        domain = "localhost"
    
    return domain


def validate_domain(domain: str) -> bool:
    """
    Validate that a string is a valid hostname.
    Must have at least one dot and only valid hostname chars,
    or be 'localhost'.
    """
    if not domain or len(domain) < 3:
        return False
    
    # Allow localhost (already normalized from 127.0.0.1)
    if domain == "localhost":
        return True
    
    # Basic hostname pattern: alphanumeric + hyphens, separated by dots
    pattern = r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'
    return bool(re.match(pattern, domain))


async def create_app(
    user_id: UUID,
    company_name: str,
    domain_url: str,
    db: Session,
) -> dict:
    """
    Create a new app registration.
    
    STEP 1: User clicked "Create app"
    STEP 2: Backend creates app record
    
    Args:
        user_id: UUID of the authenticated user
        company_name: Company name
        domain_url: Raw domain URL (will be normalized)
        db: SQLAlchemy session
    
    Returns:
        dict with created app details
    """
    start_time = time.time()
    
    # [STEP 1] User clicked "Create app"
    logger.info(
        f"[APP][STEP 1] User {str(user_id)[:8]}... clicked \"Create app\""
    )
    
    # Normalize domain
    normalized = normalize_domain(domain_url)
    
    # Validate
    if not normalized or not validate_domain(normalized):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid domain URL: '{domain_url}'. Please provide a valid hostname (e.g. 'fedex.com').",
        )
    
    if not company_name or not company_name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company name is required.",
        )
    
    # Create app record
    app = AppModel(
        created_by=user_id,
        company_name=company_name.strip(),
        domain_url=normalized,
        is_active=True,
    )
    
    db.add(app)
    db.commit()
    db.refresh(app)
    
    duration_ms = int((time.time() - start_time) * 1000)
    
    # [STEP 2] App created
    logger.info(
        f"[APP][STEP 2] App created — app_id: {str(app.app_id)[:8]}..., "
        f"domain: {normalized}, user: {str(user_id)[:8]}... — duration: {duration_ms}ms"
    )
    
    return {
        "message": "App created successfully",
        "app": {
            "app_id": app.app_id,
            "company_name": app.company_name,
            "domain_url": app.domain_url,
            "is_active": app.is_active,
            "created_at": app.created_at,
        },
    }


async def list_apps(
    user_id: UUID,
    db: Session,
) -> dict:
    """
    List all active apps for the current user.
    
    STEP 3: App list refreshed
    
    Args:
        user_id: UUID of the authenticated user
        db: SQLAlchemy session
    
    Returns:
        dict with list of apps
    """
    start_time = time.time()
    
    apps = (
        db.query(AppModel)
        .filter(
            and_(
                AppModel.created_by == user_id,
                AppModel.is_active == True,
            )
        )
        .order_by(AppModel.created_at.desc())
        .all()
    )
    
    duration_ms = int((time.time() - start_time) * 1000)
    
    # [STEP 3] App list refreshed
    logger.info(
        f"[APP][STEP 3] App list refreshed — {len(apps)} apps visible "
        f"for user {str(user_id)[:8]}... — duration: {duration_ms}ms"
    )
    
    return {
        "message": f"{len(apps)} apps found",
        "apps": [
            {
                "app_id": app.app_id,
                "company_name": app.company_name,
                "domain_url": app.domain_url,
                "is_active": app.is_active,
                "created_at": app.created_at,
            }
            for app in apps
        ],
    }


async def delete_app(
    app_id: UUID,
    user_id: UUID,
    db: Session,
) -> dict:
    """
    Soft-delete an app (set is_active = false).
    
    Args:
        app_id: UUID of the app to delete
        user_id: UUID of the authenticated user
        db: SQLAlchemy session
    
    Returns:
        dict with deletion result
    """
    start_time = time.time()
    
    app = db.query(AppModel).filter(
        and_(
            AppModel.app_id == app_id,
            AppModel.created_by == user_id,
        )
    ).first()
    
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="App not found",
        )
    
    if not app.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="App is already deleted",
        )
    
    app.is_active = False
    db.commit()
    
    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        f"[APP] App soft-deleted — app_id: {str(app_id)[:8]}..., "
        f"user: {str(user_id)[:8]}... — duration: {duration_ms}ms"
    )
    
    return {
        "message": "App deleted successfully",
        "app_id": app_id,
    }
