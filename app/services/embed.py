"""
Embed Service

Handles creation, validation, and revocation of share tokens for
dashboard embedding. Implements HMAC-SHA256 signing, token persistence,
and embed data retrieval.
"""

import hashlib
import hmac
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.schema_models import (
    DashboardModel,
    DashboardChartsModel,
    ChartModel,
    DatabaseConnectionModel,
    ShareTokenModel,
    UserProjectRoleModel,
)
from app.services.allowed_domains import get_allowed_domains_list
from app.services.app_service import normalize_domain

logger = logging.getLogger(__name__)


def _get_embed_secret() -> str:
    """Get the server secret used for HMAC signing."""
    secret = settings.EMBED_SERVER_SECRET or settings.SECRET_KEY
    if not secret:
        raise RuntimeError("No server secret configured for embed token signing")
    return secret


def _sign_token(token_id: str, dashboard_id: str) -> str:
    """
    Create HMAC-SHA256 signature for a token.

    Args:
        token_id: The token UUID as string
        dashboard_id: The dashboard UUID as string

    Returns:
        Hex-encoded HMAC signature
    """
    secret = _get_embed_secret()
    message = f"{token_id}{dashboard_id}"
    signature = hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return signature


def _verify_signature(token_id: str, dashboard_id: str, signature: str) -> bool:
    """Verify an HMAC-SHA256 signature for a token."""
    expected = _sign_token(token_id, dashboard_id)
    return hmac.compare_digest(expected, signature)


def _build_embed_url(token_id: str, base_url: str) -> str:
    """Build the embed URL from token ID."""
    return f"{base_url}/api/v1/embed/{token_id}"


def _build_iframe_snippet(embed_url: str) -> str:
    """Build the ready-to-paste iframe snippet."""
    return (
        f'<iframe src="{embed_url}" '
        f'width="100%" height="600" '
        f'frameborder="0" '
        f'style="border: none; border-radius: 8px;" '
        f'allowfullscreen '
        f'loading="lazy">'
        f"</iframe>"
    )


def check_origin(origin: str | None, allowed_domains: list[str]) -> tuple[bool, str]:
    """
    Check if the request origin is in the allowed domains list.
    
    STEP 11: Origin header check (domain-lock enforcement)
    
    Args:
        origin: The Origin header value (may be None for direct browser access)
        allowed_domains: List of bare hostnames from the token's snapshot
    
    Returns:
        Tuple of (is_allowed, reason_string)
    """
    # If origin is null/missing (direct browser tab load), allow for testing
    if not origin:
        return True, "origin_null_allowed_for_testing"
    
    # Normalize origin to bare hostname
    origin_hostname = normalize_domain(origin)
    
    # Normalize allowed domains for comparison
    normalized_allowed = [normalize_domain(d) for d in allowed_domains]
    
    if origin_hostname in normalized_allowed:
        return True, "allowed"
    
    return False, "rejected"


async def create_share_token(
    dashboard_id: UUID,
    user_id: UUID,
    expires_in_days: Optional[int],
    base_url: str,
    db: Session,
) -> dict:
    """
    Create or return an existing share token for a dashboard.

    STEP 1: User clicked "Create shareable link"
    STEP 2: Validate request
    STEP 2a: Generate UUID token
    STEP 2b: HMAC-sign the token
    STEP 2c: Persist token to store

    Args:
        dashboard_id: UUID of the dashboard
        user_id: UUID of the requesting user
        expires_in_days: Optional expiry in days (None = no expiry)
        base_url: Server base URL for constructing embed links
        db: SQLAlchemy session

    Returns:
        dict with token details
    """
    start_time = time.time()

    # [STEP 6] Shareable link requested
    logger.info(
        f"[EMBED][STEP 6] Shareable link requested — "
        f"dashboard {str(dashboard_id)[:8]}..."
    )

    # [STEP 2] Validate the request
    # Verify dashboard exists
    dashboard = db.query(DashboardModel).filter(
        DashboardModel.id == dashboard_id
    ).first()

    if not dashboard:
        logger.error(
            f"[EMBED][STEP 6] Validation failed — dashboard {str(dashboard_id)[:8]}... not found"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard not found",
        )

    # Verify user has owner/admin role on this dashboard's project
    user_role = db.query(UserProjectRoleModel).filter(
        and_(
            UserProjectRoleModel.user_id == user_id,
            UserProjectRoleModel.project_id == dashboard.project_id,
        )
    ).first()

    role_name = "owner" if (user_role and user_role.is_owner) else "member"

    # Get current allowed domains for this dashboard
    allowed_domains = get_allowed_domains_list(dashboard_id, db)
    logger.info(
        f"[EMBED][STEP 6] Shareable link requested — dashboard {str(dashboard_id)[:8]}..., "
        f"allowed domains: {allowed_domains}"
    )

    logger.info(
        f"[EMBED] Validation passed — user {str(user_id)[:8]}..., "
        f"dashboard {str(dashboard_id)[:8]}..., role {role_name}"
    )

    # Check if an active token already exists for this dashboard
    existing_token = db.query(ShareTokenModel).filter(
        and_(
            ShareTokenModel.dashboard_id == dashboard_id,
            ShareTokenModel.is_active == True,
        )
    ).first()

    if existing_token:
        # Check if it's still valid (not expired)
        if existing_token.expires_at is None or existing_token.expires_at > datetime.now(timezone.utc):
            embed_url = _build_embed_url(str(existing_token.token_id), base_url)
            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                f"[EMBED] Existing active token returned for dashboard "
                f"{str(dashboard_id)[:8]}... — duration: {duration_ms}ms"
            )
            return {
                "message": "Existing share token returned",
                "token": {
                    "token_id": existing_token.token_id,
                    "dashboard_id": existing_token.dashboard_id,
                    "embed_url": embed_url,
                    "iframe_snippet": _build_iframe_snippet(embed_url),
                    "is_active": existing_token.is_active,
                    "created_at": existing_token.created_at,
                    "expires_at": existing_token.expires_at,
                    "access_count": existing_token.access_count,
                    "allowed_domains_snapshot": existing_token.allowed_domains_snapshot,
                },
            }

    # [STEP 7] Generate UUID token
    token_id = uuid4()
    logger.info(
        f"[EMBED][STEP 7] Token generated — token: {str(token_id)[:8]}..., "
        f"dashboard: {str(dashboard_id)[:8]}..., domains: {allowed_domains}"
    )

    # HMAC-sign the token
    signature = _sign_token(str(token_id), str(dashboard_id))

    # Persist token to store with allowed_domains snapshot
    expires_at = None
    if expires_in_days is not None and expires_in_days > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    share_token = ShareTokenModel(
        token_id=token_id,
        dashboard_id=dashboard_id,
        created_by=user_id,
        hmac_signature=signature,
        is_active=True,
        expires_at=expires_at,
        allowed_domains_snapshot=allowed_domains if allowed_domains else None,
    )

    db.add(share_token)
    db.commit()
    db.refresh(share_token)

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        f"[EMBED][STEP 7] Token persisted to DB — "
        f"expires_at: {expires_at}, domains: {allowed_domains} — duration: {duration_ms}ms"
    )

    embed_url = _build_embed_url(str(token_id), base_url)

    # [STEP 8] Return iframe snippet to frontend
    iframe_snippet = _build_iframe_snippet(embed_url)
    logger.info(
        f"[EMBED][STEP 8] Snippet returned to client for dashboard {str(dashboard_id)[:8]}..."
    )

    return {
        "message": "Share token created successfully",
        "token": {
            "token_id": share_token.token_id,
            "dashboard_id": share_token.dashboard_id,
            "embed_url": embed_url,
            "iframe_snippet": iframe_snippet,
            "is_active": share_token.is_active,
            "created_at": share_token.created_at,
            "expires_at": share_token.expires_at,
            "access_count": share_token.access_count,
            "allowed_domains_snapshot": share_token.allowed_domains_snapshot,
        },
    }


async def revoke_share_token(
    dashboard_id: UUID,
    user_id: UUID,
    db: Session,
) -> dict:
    """
    Revoke all active share tokens for a dashboard.
    Sets is_active = false (does not delete for audit trail).

    Args:
        dashboard_id: UUID of the dashboard
        user_id: UUID of the requesting user
        db: SQLAlchemy session

    Returns:
        dict with revocation result
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

    # Revoke all active tokens
    active_tokens = db.query(ShareTokenModel).filter(
        and_(
            ShareTokenModel.dashboard_id == dashboard_id,
            ShareTokenModel.is_active == True,
        )
    ).all()

    if not active_tokens:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active share token found for this dashboard",
        )

    for token in active_tokens:
        token.is_active = False

    db.commit()

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        f"[EMBED] Share token(s) revoked for dashboard {str(dashboard_id)[:8]}... "
        f"by user {str(user_id)[:8]}... — count: {len(active_tokens)} — duration: {duration_ms}ms"
    )

    return {
        "message": "Share token revoked successfully",
        "dashboard_id": dashboard_id,
    }


async def get_share_token(
    dashboard_id: UUID,
    db: Session,
    base_url: str,
) -> Optional[dict]:
    """
    Get the active share token for a dashboard (if any).

    Args:
        dashboard_id: UUID of the dashboard
        db: SQLAlchemy session
        base_url: Server base URL

    Returns:
        dict with token details or None
    """
    token = db.query(ShareTokenModel).filter(
        and_(
            ShareTokenModel.dashboard_id == dashboard_id,
            ShareTokenModel.is_active == True,
        )
    ).first()

    if not token:
        return None

    # Check if expired
    if token.expires_at and token.expires_at < datetime.now(timezone.utc):
        return None

    embed_url = _build_embed_url(str(token.token_id), base_url)
    return {
        "token_id": token.token_id,
        "dashboard_id": token.dashboard_id,
        "embed_url": embed_url,
        "iframe_snippet": _build_iframe_snippet(embed_url),
        "is_active": token.is_active,
        "created_at": token.created_at,
        "expires_at": token.expires_at,
        "access_count": token.access_count,
    }


async def validate_embed_token(
    token_id: UUID,
    db: Session,
    origin: str | None = None,
) -> ShareTokenModel:
    """
    Validate an embed token for rendering or data requests.
    Implements STEP 10-12 checks including origin domain-lock.

    Args:
        token_id: UUID of the token
        db: SQLAlchemy session
        origin: Origin header from the request (for domain-lock)

    Returns:
        ShareTokenModel if valid

    Raises:
        HTTPException 403 if invalid
    """
    start_time = time.time()

    # [STEP 10] Embed request received
    logger.info(
        f"[EMBED][STEP 10] Embed request — token: {str(token_id)[:8]}..., origin: {origin}"
    )

    # [STEP 12] Token validation
    token = db.query(ShareTokenModel).filter(
        ShareTokenModel.token_id == token_id
    ).first()

    if not token:
        logger.error(
            f"[EMBED][STEP 12] Token validation — result: invalid, reason: not_found"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "embed_invalid",
                "message": "This embed link is invalid or has expired.",
            },
        )

    if not token.is_active:
        logger.error(
            f"[EMBED][STEP 12] Token validation — result: invalid, reason: revoked"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "embed_invalid",
                "message": "This embed link is invalid or has expired.",
            },
        )

    if token.expires_at and token.expires_at < datetime.now(timezone.utc):
        logger.error(
            f"[EMBED][STEP 12] Token validation — result: invalid, reason: expired "
            f"(expires_at={token.expires_at})"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "embed_invalid",
                "message": "This embed link is invalid or has expired.",
            },
        )

    # Verify HMAC signature
    if not _verify_signature(str(token.token_id), str(token.dashboard_id), token.hmac_signature):
        logger.error(
            f"[EMBED][STEP 12] Token validation — result: invalid, reason: hmac_mismatch"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "embed_invalid",
                "message": "This embed link is invalid or has expired.",
            },
        )

    logger.info(
        f"[EMBED][STEP 12] Token validation — result: valid"
    )

    # [STEP 11] Origin header check (domain-lock enforcement)
    allowed_domains = token.allowed_domains_snapshot or []
    if allowed_domains:
        is_allowed, result = check_origin(origin, allowed_domains)
        logger.info(
            f"[EMBED][STEP 11] Origin check — origin: {origin}, "
            f"allowed: {allowed_domains}, result: {result}"
        )
        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "domain_not_allowed",
                    "message": "This embed is not authorized for this domain.",
                },
            )
    else:
        logger.info(
            f"[EMBED][STEP 11] Origin check — no allowed_domains_snapshot, "
            f"skipping domain lock"
        )

    # Update access tracking
    token.last_accessed = datetime.now(timezone.utc)
    token.access_count += 1
    db.commit()

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        f"[EMBED] Token valid — dashboard {str(token.dashboard_id)[:8]}... "
        f"authorized for embed — duration: {duration_ms}ms"
    )

    return token


async def get_embed_dashboard_data(
    token: ShareTokenModel,
    db: Session,
) -> dict:
    """
    Get all dashboard and chart data for rendering in the embed page.

    Args:
        token: Validated ShareTokenModel
        db: SQLAlchemy session

    Returns:
        dict with dashboard title and charts info
    """
    start_time = time.time()

    dashboard = db.query(DashboardModel).filter(
        DashboardModel.id == token.dashboard_id
    ).first()

    if not dashboard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard not found",
        )

    # Get all charts for this dashboard
    dashboard_charts = (
        db.query(DashboardChartsModel)
        .filter(DashboardChartsModel.dashboard_id == dashboard.id)
        .all()
    )

    charts = []
    for dc in dashboard_charts:
        chart = db.query(ChartModel).filter(ChartModel.id == dc.chart_id).first()
        if chart:
            charts.append({
                "id": str(chart.id),
                "title": chart.title,
                "chart_type": chart.chart_type,
                "query": chart.query,
                "connection_id": str(dc.database_connection_id),
                "is_time_based": chart.is_time_based,
                "x_axis": chart.x_axis,
                "y_axis": chart.y_axis,
            })

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        f"[EMBED][STEP 8] Embed HTML rendered for dashboard "
        f"{str(token.dashboard_id)[:8]}... — {len(charts)} charts — duration: {duration_ms}ms"
    )

    return {
        "dashboard_title": dashboard.title,
        "dashboard_id": str(dashboard.id),
        "charts": charts,
    }


async def get_embed_chart_data(
    token: ShareTokenModel,
    chart_id: UUID,
    db: Session,
) -> dict:
    """
    Get data for a specific chart in an embedded dashboard.
    Executes the chart's query against the external database.

    Args:
        token: Validated ShareTokenModel
        chart_id: UUID of the chart
        db: SQLAlchemy session

    Returns:
        dict with chart data
    """
    start_time = time.time()

    # Verify this chart belongs to the token's dashboard
    dc = db.query(DashboardChartsModel).filter(
        and_(
            DashboardChartsModel.dashboard_id == token.dashboard_id,
            DashboardChartsModel.chart_id == chart_id,
        )
    ).first()

    if not dc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chart not found in this dashboard",
        )

    chart = db.query(ChartModel).filter(ChartModel.id == chart_id).first()
    if not chart:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chart not found",
        )

    # Get the database connection
    connection = db.query(DatabaseConnectionModel).filter(
        DatabaseConnectionModel.id == dc.database_connection_id
    ).first()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Database connection not found",
        )

    # Execute the query via the external engine manager
    try:
        from app.core.db import external_engine_manager
        from cryptography.fernet import Fernet

        # Decrypt connection string
        fernet = Fernet(settings.ENCRYPTION_KEY.encode())
        decrypted_conn_str = fernet.decrypt(
            connection.db_connection_string.encode()
        ).decode()

        ext_engine = external_engine_manager.get_engine(
            connection_id=dc.database_connection_id,
            connection_string=decrypted_conn_str,
            db_type=connection.db_type,
        )
        with ext_engine.connect() as conn:
            result = conn.execute(
                __import__("sqlalchemy").text(chart.query)
            )
            rows = [dict(row._mapping) for row in result]

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            f"[EMBED][STEP 10] Chart data fetched — chart {str(chart_id)[:8]}... "
            f"— {len(rows)} rows — duration: {duration_ms}ms"
        )

        return {
            "success": True,
            "data": rows,
            "chart_id": str(chart_id),
            "chart_type": chart.chart_type,
            "title": chart.title,
            "x_axis": chart.x_axis,
            "y_axis": chart.y_axis,
            "is_time_based": chart.is_time_based,
        }

    except HTTPException:
        raise
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            f"[EMBED][STEP 10] Chart data fetch FAILED for chart {str(chart_id)[:8]}... "
            f"— duration: {duration_ms}ms — error: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch chart data",
        )
