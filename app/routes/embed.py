"""
Embed Routes

API routes for creating, revoking, and serving embedded dashboards.

Routes:
    POST   /api/v1/backend/dashboards/{id}/share-token  → create or return existing token
    GET    /api/v1/backend/dashboards/{id}/share-token   → get existing token info
    DELETE /api/v1/backend/dashboards/{id}/share-token   → revoke (set is_active = false)
    GET    /api/v1/embed/{token_id}                      → render standalone embed HTML
    GET    /api/v1/embed/{token_id}/data/{chart_id}      → serve chart data (JWT-gated)
    GET    /api/v1/embed/{token_id}/dashboard             → current dashboard metadata
    POST   /api/v1/embed/token/refresh                   → refresh embed JWT
"""

import logging
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
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
    get_embed_dashboard_data_by_dashboard_id,
    get_embed_chart_data_by_dashboard,
    get_embed_chart_date_range,
    refresh_embed_jwt,
)
from app.utils.embed_jwt import issue_embed_jwt, verify_embed_jwt

logger = logging.getLogger(__name__)

share_token_router = APIRouter(prefix="/api/v1/backend", tags=["share-token"])
embed_router = APIRouter(prefix="/api/v1/embed", tags=["embed"])


def _extract_bearer(request: Request) -> str | None:
    auth_header = request.headers.get("authorization") or request.headers.get(
        "Authorization"
    )
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return None


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
    user_id = UUID(token_payload.get("sub"))
    result = await revoke_share_token(
        dashboard_id=dashboard_id,
        user_id=user_id,
        db=db,
    )
    return result


def _get_embed_html(
    dashboard_title: str,
    dashboard_data: dict,
    token_id: str,
    api_base: str,
    token_bundle: dict,
) -> str:
    import json

    charts = dashboard_data.get("charts", [])
    assets_base = f"{api_base}/api/v1/embed/assets"
    embed_config = {
        "tokenId": token_id,
        "apiBase": api_base,
        "dashboardTitle": dashboard_title,
        "charts": charts,
        "assetsBase": assets_base,
        "accessToken": token_bundle["access_token"],
        "expiresIn": token_bundle["expires_in"],
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
    start_time = time.time()
    origin = request.headers.get("origin") or request.headers.get("Origin")

    token = await validate_embed_token(token_id, db, origin=origin)
    dashboard_data = await get_embed_dashboard_data(token, db)
    token_bundle = issue_embed_jwt(token)

    api_base = str(request.base_url).rstrip("/")
    html = _get_embed_html(
        dashboard_title=dashboard_data["dashboard_title"],
        dashboard_data=dashboard_data,
        token_id=str(token_id),
        api_base=api_base,
        token_bundle=token_bundle,
    )

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        f"[EMBED][STEP 2d] CORS and CSP headers configured on embed route — duration: {duration_ms}ms"
    )

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
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
):
    origin = request.headers.get("origin") or request.headers.get("Origin")
    bearer = _extract_bearer(request)
    if not bearer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "jwt_invalid",
                "message": "Authorization Bearer token required.",
            },
        )

    claims = verify_embed_jwt(bearer, origin=origin)
    if claims.share_token_id != token_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "jwt_invalid",
                "message": "Token does not match embed session.",
            },
        )

    data = await get_embed_chart_data_by_dashboard(
        claims.dashboard_id, chart_id, db,
        start_date=start_date,
        end_date=end_date,
    )

    response = JSONResponse(content=data)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cache-Control"] = "no-store"
    return response


@embed_router.get("/{token_id}/data/{chart_id}/date-range")
async def get_embed_chart_date_range_route(
    request: Request,
    token_id: UUID = Path(..., description="Share token ID"),
    chart_id: UUID = Path(..., description="Chart ID"),
    db: Session = Depends(get_db),
):
    """
    Return the min and max date values for a time-based chart's stored query.

    The frontend uses these bounds to initialise the DateRangePicker and
    constrain the calendar to dates that actually exist in the data.

    Response:
        200 { "min_date": "YYYY-MM-DD", "max_date": "YYYY-MM-DD",
               "date_column": str, "is_time_based": bool }
    """
    origin = request.headers.get("origin") or request.headers.get("Origin")
    bearer = _extract_bearer(request)
    if not bearer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "jwt_invalid",
                "message": "Authorization Bearer token required.",
            },
        )

    claims = verify_embed_jwt(bearer, origin=origin)
    if claims.share_token_id != token_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "jwt_invalid",
                "message": "Token does not match embed session.",
            },
        )

    data = await get_embed_chart_date_range(
        claims.dashboard_id, chart_id, db
    )

    response = JSONResponse(content=data)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cache-Control"] = "no-store"
    return response



@embed_router.get("/{token_id}/dashboard")
async def get_embed_dashboard_metadata_route(
    request: Request,
    token_id: UUID = Path(..., description="Share token ID"),
    db: Session = Depends(get_db),
):
    origin = request.headers.get("origin") or request.headers.get("Origin")
    bearer = _extract_bearer(request)
    if not bearer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "jwt_invalid",
                "message": "Authorization Bearer token required.",
            },
        )

    claims = verify_embed_jwt(bearer, origin=origin)
    if claims.share_token_id != token_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "jwt_invalid",
                "message": "Token does not match embed session.",
            },
        )

    data = await get_embed_dashboard_data_by_dashboard_id(claims.dashboard_id, db)

    response = JSONResponse(content=data)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cache-Control"] = "no-store"
    return response


class RefreshTokenRequest(BaseModel):
    share_token: str


@embed_router.post("/token/refresh")
async def refresh_token_route(
    request: Request,
    body: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    origin = request.headers.get("origin") or request.headers.get("Origin")
    bearer = _extract_bearer(request)
    if not bearer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "jwt_invalid",
                "message": "Authorization Bearer token required.",
            },
        )

    share_token_id = UUID(body.share_token)
    result = await refresh_embed_jwt(
        raw_jwt=bearer,
        share_token_id=share_token_id,
        db=db,
        origin=origin,
    )

    response = JSONResponse(content=result)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cache-Control"] = "no-store"
    return response
