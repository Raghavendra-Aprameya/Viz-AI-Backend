"""
Embed Routes

API routes for creating, revoking, and serving embedded dashboards.

Routes:
    POST   /api/v1/backend/dashboards/{id}/share-token  → create or return existing token
    GET    /api/v1/backend/dashboards/{id}/share-token   → get existing token info
    DELETE /api/v1/backend/dashboards/{id}/share-token   → revoke (set is_active = false)
    GET    /api/v1/embed/{token_id}                      → render standalone embed HTML
    GET    /api/v1/embed/{token_id}/data/{chart_id}      → serve chart data (token-gated)
"""

import logging
import time
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.utils.token_parser import get_current_user
from app.schemas import (
    CreateShareTokenRequest,
    CreateShareTokenResponse,
    RevokeShareTokenResponse,
)
from app.services.embed import (
    create_share_token,
    revoke_share_token,
    get_share_token,
    validate_embed_token,
    get_embed_dashboard_data,
    get_embed_chart_data,
)

logger = logging.getLogger(__name__)

# Router for authenticated share-token management (under /api/v1/backend)
share_token_router = APIRouter(prefix="/api/v1/backend", tags=["share-token"])

# Router for public embed endpoints (no auth required)
embed_router = APIRouter(prefix="/api/v1/embed", tags=["embed"])


# ============================================================================
# SHARE TOKEN MANAGEMENT (authenticated)
# ============================================================================


@share_token_router.post(
    "/dashboards/{dashboard_id}/share-token",
    status_code=status.HTTP_200_OK,
    response_model=CreateShareTokenResponse,
)
async def create_share_token_route(
    request: Request,
    dashboard_id: UUID = Path(..., description="Dashboard ID to create share token for"),
    data: CreateShareTokenRequest = None,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Create a shareable embed token for a dashboard.
    If an active token already exists, returns the existing one.
    """
    user_id = UUID(token_payload.get("sub"))
    base_url = str(request.base_url).rstrip("/")

    expires_in_days = data.expires_in_days if data else None

    result = await create_share_token(
        dashboard_id=dashboard_id,
        user_id=user_id,
        expires_in_days=expires_in_days,
        base_url=base_url,
        db=db,
    )
    return result


@share_token_router.get(
    "/dashboards/{dashboard_id}/share-token",
    status_code=status.HTTP_200_OK,
)
async def get_share_token_route(
    request: Request,
    dashboard_id: UUID = Path(..., description="Dashboard ID to get share token for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Get the active share token for a dashboard, if one exists.
    """
    base_url = str(request.base_url).rstrip("/")
    token = await get_share_token(dashboard_id, db, base_url)

    if not token:
        return {"message": "No active share token found", "token": None}

    return {"message": "Active share token found", "token": token}


@share_token_router.delete(
    "/dashboards/{dashboard_id}/share-token",
    status_code=status.HTTP_200_OK,
    response_model=RevokeShareTokenResponse,
)
async def revoke_share_token_route(
    dashboard_id: UUID = Path(..., description="Dashboard ID to revoke share token for"),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Revoke the active share token for a dashboard.
    Sets is_active = false (does not delete for audit trail).
    """
    user_id = UUID(token_payload.get("sub"))
    result = await revoke_share_token(
        dashboard_id=dashboard_id,
        user_id=user_id,
        db=db,
    )
    return result


# ============================================================================
# PUBLIC EMBED ENDPOINTS (no auth required)
# ============================================================================


def _get_embed_html(dashboard_title: str, dashboard_data: dict, token_id: str, api_base: str) -> str:
    """Generate the standalone embed HTML shell (ECharts bundle loaded from static assets)."""
    import json

    charts = dashboard_data.get("charts", [])
    assets_base = f"{api_base}/api/v1/embed/assets"
    embed_config = {
        "tokenId": token_id,
        "apiBase": api_base,
        "dashboardTitle": dashboard_title,
        "charts": charts,
        "assetsBase": assets_base,
    }
    config_json = json.dumps(embed_config)

    return f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{dashboard_title} — VizAI Embed</title>
    <link rel="stylesheet" href="{assets_base}/embed.css">
</head>
<body>
    <div id="embed-root"></div>
    <script>
        window.__VIZAI_EMBED__ = {config_json};
    </script>
    <script type="module" src="{assets_base}/embed.js"></script>
</body>
</html>"""


@embed_router.get("/{token_id}")
async def render_embed_page(
    request: Request,
    token_id: UUID = Path(..., description="Share token ID"),
    db: Session = Depends(get_db),
):
    """
    Render a standalone HTML page for the embedded dashboard.
    No authentication required — access controlled by token validation.

    [STEP 2d] CORS and CSP headers configured on embed route.
    [STEP 8] Dashboard HTML returned.
    """
    start_time = time.time()

    # Extract Origin header for domain-lock check
    origin = request.headers.get("origin") or request.headers.get("Origin")

    # Validate token (STEP 10 + 11 + 12)
    token = await validate_embed_token(token_id, db, origin=origin)

    # Get dashboard data (STEP 8)
    dashboard_data = await get_embed_dashboard_data(token, db)

    api_base = str(request.base_url).rstrip("/")
    html = _get_embed_html(
        dashboard_title=dashboard_data["dashboard_title"],
        dashboard_data=dashboard_data,
        token_id=str(token_id),
        api_base=api_base,
    )

    duration_ms = int((time.time() - start_time) * 1000)

    # [STEP 2d] CORS and CSP headers
    logger.info(f"[EMBED][STEP 2d] CORS and CSP headers configured on embed route — duration: {duration_ms}ms")

    response = HTMLResponse(content=html, status_code=200)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["X-Frame-Options"] = "ALLOWALL"
    response.headers["Content-Security-Policy"] = "frame-ancestors *"
    response.headers["Cache-Control"] = "no-store"

    return response


@embed_router.get("/{token_id}/data/{chart_id}")
async def get_embed_chart_data_route(
    request: Request,
    token_id: UUID = Path(..., description="Share token ID"),
    chart_id: UUID = Path(..., description="Chart ID"),
    db: Session = Depends(get_db),
):
    """
    Serve chart data for an embedded dashboard chart.
    Token validated on each data request (same as STEP 10-12).

    [STEP 14] Charts fetch data via API.
    """
    # Extract Origin header for domain-lock check
    origin = request.headers.get("origin") or request.headers.get("Origin")

    # Validate token
    token = await validate_embed_token(token_id, db, origin=origin)

    # Get chart data (STEP 10)
    data = await get_embed_chart_data(token, chart_id, db)

    response = JSONResponse(content=data)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cache-Control"] = "no-store"

    return response
