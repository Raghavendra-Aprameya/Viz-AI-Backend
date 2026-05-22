"""
Stateless JWT helpers for embedded dashboard sessions.

Claims: typ, st (share token id), did (dashboard id), origins (normalized hostnames).
Chart membership is NOT in the JWT — validated per request via DB.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

import jwt
from fastapi import HTTPException, status

from app.core.settings import settings
from app.models.schema_models import ShareTokenModel
from app.services.app_service import normalize_domain

EMBED_JWT_TYPE = "embed"
EMBED_JWT_REFRESH_GRACE_MINUTES = 35


def _jwt_ttl_minutes() -> int:
    return getattr(settings, "EMBED_JWT_EXPIRE_MINUTES", 30) or 30


def _get_embed_jwt_secret() -> str:
    secret = settings.EMBED_SERVER_SECRET or settings.SECRET_KEY
    if not secret:
        raise RuntimeError("No server secret configured for embed JWT signing")
    return secret


def _normalized_origins_from_share(share: ShareTokenModel) -> List[str]:
    raw = share.allowed_domains_snapshot or []
    return [normalize_domain(d) for d in raw]


def _check_origin_against_claims(
    origin: Optional[str], allowed_origins: List[str]
) -> None:
    """Enforce domain lock from JWT origins claim (empty list = no lock)."""
    if not allowed_origins:
        return
    if not origin:
        return
    origin_hostname = normalize_domain(origin)
    if origin_hostname not in allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "origin_not_allowed",
                "message": "This embed is not authorized for this domain.",
            },
        )


@dataclass(frozen=True)
class EmbedJwtClaims:
    share_token_id: UUID
    dashboard_id: UUID
    origins: List[str]


def issue_embed_jwt(share: ShareTokenModel) -> dict:
    """
    Issue a 30-minute embed JWT for chart/dashboard API calls.
    """
    now = datetime.now(timezone.utc)
    ttl = _jwt_ttl_minutes()
    expire = now + timedelta(minutes=ttl)
    origins = _normalized_origins_from_share(share)

    payload = {
        "typ": EMBED_JWT_TYPE,
        "st": str(share.token_id),
        "did": str(share.dashboard_id),
        "origins": origins,
        "iat": now,
        "exp": expire,
    }

    token = jwt.encode(
        payload,
        _get_embed_jwt_secret(),
        algorithm=settings.ALGORITHM,
    )

    return {
        "access_token": token,
        "expires_in": ttl * 60,
    }


def _payload_to_claims(payload: dict) -> EmbedJwtClaims:
    if payload.get("typ") != EMBED_JWT_TYPE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "jwt_invalid",
                "message": "Invalid embed token.",
            },
        )

    try:
        return EmbedJwtClaims(
            share_token_id=UUID(payload["st"]),
            dashboard_id=UUID(payload["did"]),
            origins=list(payload.get("origins") or []),
        )
    except (KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "jwt_invalid",
                "message": "Invalid embed token.",
            },
        ) from None


def verify_embed_jwt(raw: str, origin: Optional[str] = None) -> EmbedJwtClaims:
    """
    Verify embed JWT (signature, exp, typ, origin). No database access.
    """
    try:
        payload = jwt.decode(
            raw,
            _get_embed_jwt_secret(),
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "iat", "st", "did", "typ"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "jwt_expired",
                "message": "Embed session expired.",
            },
        ) from None
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "jwt_invalid",
                "message": "Invalid embed token.",
            },
        ) from None

    claims = _payload_to_claims(payload)
    _check_origin_against_claims(origin, claims.origins)
    return claims


def decode_embed_jwt_for_refresh(raw: str) -> EmbedJwtClaims:
    """
    Verify signature for refresh; allow expired JWT within grace window after iat.
    Does not check Origin (refresh handler re-validates share + origin via DB).
    """
    try:
        payload = jwt.decode(
            raw,
            _get_embed_jwt_secret(),
            algorithms=[settings.ALGORITHM],
            options={
                "verify_exp": False,
                "require": ["iat", "st", "did", "typ"],
            },
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "jwt_invalid",
                "message": "Invalid embed token.",
            },
        ) from None

    claims = _payload_to_claims(payload)

    iat = payload.get("iat")
    if iat is not None:
        if isinstance(iat, (int, float)):
            iat_dt = datetime.fromtimestamp(iat, tz=timezone.utc)
        else:
            iat_dt = iat if iat.tzinfo else iat.replace(tzinfo=timezone.utc)
        grace_end = iat_dt + timedelta(minutes=EMBED_JWT_REFRESH_GRACE_MINUTES)
        if datetime.now(timezone.utc) > grace_end:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "jwt_expired",
                    "message": "Embed session expired. Please reload the page.",
                },
            )

    return claims
