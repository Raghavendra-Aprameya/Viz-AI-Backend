"""
Observability API routes.

POST   /api/v1/observability/traces          — ingest a trace (LLM service → backend)
GET    /api/v1/observability/traces          — list/filter traces (paginated)
GET    /api/v1/observability/traces/{id}     — full trace detail
GET    /api/v1/observability/analytics       — aggregated usage analytics
POST   /api/v1/observability/rollup          — manually trigger daily rollup (admin only)
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.observability import (
    compute_daily_rollup,
    get_trace,
    get_usage_analytics,
    ingest_trace,
    list_traces,
)
from app.utils.token_parser import get_current_user

logger = logging.getLogger(__name__)

observability_router = APIRouter(prefix="/api/v1/observability", tags=["Observability"])


# ─── Request / Response Schemas ───────────────────────────────────────────────

class IngestTraceRequest(BaseModel):
    session_id: Optional[str] = None
    chart_id: Optional[str] = None
    project_id: Optional[str] = None
    user_id: Optional[str] = None
    ai_service: str = "probe_mode"
    llm_provider: Optional[str] = None
    model_name: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: Optional[int] = None
    prompt_text: Optional[str] = None
    completion_text: Optional[str] = None
    sql_generated: Optional[str] = None
    sql_retries: int = 0
    schema_tables_used: Optional[Any] = None
    agent_steps: Optional[Any] = None
    status: str = "success"
    error_message: Optional[str] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@observability_router.post("/traces", status_code=status.HTTP_201_CREATED)
async def ingest_trace_endpoint(
    body: IngestTraceRequest,
    db: Session = Depends(get_db),
):
    """
    Ingest a single LLM trace record.
    Called by the LLM service's async trace sink — no user auth required
    (internal service-to-service call). Auth is enforced at network level.
    """
    try:
        trace = ingest_trace(db, body.model_dump())
        return {"id": str(trace.id), "status": "created"}
    except Exception as exc:
        logger.error("Failed to ingest trace: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to persist trace")


@observability_router.get("/traces")
async def list_traces_endpoint(
    project_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    ai_service: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List traces with optional filters. Requires authentication."""
    try:
        return list_traces(
            db,
            project_id=project_id,
            user_id=user_id,
            ai_service=ai_service,
            status=status_filter,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
    except Exception as exc:
        logger.error("Failed to list traces: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch traces")


@observability_router.get("/traces/{trace_id}")
async def get_trace_endpoint(
    trace_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get full trace detail including prompt/completion text."""
    result = get_trace(db, trace_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return result


@observability_router.get("/analytics")
async def get_analytics_endpoint(
    project_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return aggregated usage analytics — token totals, cost, daily trend, service breakdown."""
    try:
        return get_usage_analytics(db, project_id=project_id, date_from=date_from, date_to=date_to)
    except Exception as exc:
        logger.error("Failed to get analytics: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to compute analytics")


@observability_router.post("/rollup")
async def trigger_rollup_endpoint(
    target_date: Optional[str] = Query(None, description="ISO date YYYY-MM-DD (default: yesterday)"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Manually trigger daily usage rollup (admin only)."""
    if not current_user.get("is_super"):
        raise HTTPException(status_code=403, detail="Super admin access required")
    try:
        parsed_date = date.fromisoformat(target_date) if target_date else None
        rows = compute_daily_rollup(db, parsed_date)
        return {"rows_written": rows, "status": "ok"}
    except Exception as exc:
        logger.error("Rollup failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Rollup failed")
