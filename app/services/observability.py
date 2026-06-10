"""
Observability service — persists LLM traces and computes roll-ups.

Token cost estimation uses litellm.model_cost (kept current by the litellm
maintainers) so pricing is always up to date without any DB edits.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.schema_models import DailyUsageRollupModel, LLMTraceModel

logger = logging.getLogger(__name__)


# ─── Cost Estimation via litellm ─────────────────────────────────────────────

def _litellm_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Use litellm.model_cost dict for per-token pricing.
    Falls back to 0.0 if model is unknown — never raises.
    """
    try:
        import litellm  # lazy import — not on the critical path

        model_cost = litellm.model_cost
        # Direct lookup first
        info = model_cost.get(model_name)
        if not info:
            # Fuzzy match: find the first key that contains the model name
            lower = model_name.lower()
            for k, v in model_cost.items():
                if lower in k.lower() and not k.startswith(("azure/", "ft:")):
                    info = v
                    break
        if not info:
            return 0.0

        ip = float(info.get("input_cost_per_token", 0))
        op = float(info.get("output_cost_per_token", 0))
        return ip * prompt_tokens + op * completion_tokens
    except Exception as exc:
        logger.debug("litellm cost estimation failed for model=%s: %s", model_name, exc)
        return 0.0


def estimate_cost(
    db: Session,  # kept for signature compatibility; unused now
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> Decimal:
    """Return estimated USD cost using live litellm pricing."""
    return Decimal(str(_litellm_cost(model_name, prompt_tokens, completion_tokens)))


# ─── Trace Ingestion ──────────────────────────────────────────────────────────

def ingest_trace(db: Session, payload: Dict[str, Any]) -> LLMTraceModel:
    """Persist a single LLM trace record and return it."""
    prompt_tokens = int(payload.get("prompt_tokens") or 0)
    completion_tokens = int(payload.get("completion_tokens") or 0)
    total_tokens = prompt_tokens + completion_tokens
    model_name = payload.get("model_name") or ""

    cost = estimate_cost(db, model_name, prompt_tokens, completion_tokens)

    trace = LLMTraceModel(
        id=uuid4(),
        session_id=payload.get("session_id"),
        chart_id=_safe_uuid(payload.get("chart_id")),
        project_id=_safe_uuid(payload.get("project_id")),
        user_id=_safe_uuid(payload.get("user_id")),
        ai_service=payload.get("ai_service", "probe_mode"),
        llm_provider=payload.get("llm_provider"),
        model_name=model_name or None,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=cost,
        latency_ms=payload.get("latency_ms"),
        prompt_text=_truncate(payload.get("prompt_text"), 20000),
        completion_text=_truncate(payload.get("completion_text"), 10000),
        sql_generated=payload.get("sql_generated"),
        sql_retries=int(payload.get("sql_retries") or 0),
        schema_tables_used=payload.get("schema_tables_used"),
        agent_steps=payload.get("agent_steps"),
        status=payload.get("status", "success"),
        error_message=_truncate(payload.get("error_message"), 2000),
    )
    db.add(trace)
    db.commit()
    db.refresh(trace)
    return trace


# ─── Trace Queries ────────────────────────────────────────────────────────────

def list_traces(
    db: Session,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    ai_service: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> Dict[str, Any]:
    q = db.query(LLMTraceModel)

    if project_id:
        q = q.filter(LLMTraceModel.project_id == _safe_uuid(project_id))
    if user_id:
        q = q.filter(LLMTraceModel.user_id == _safe_uuid(user_id))
    if ai_service:
        q = q.filter(LLMTraceModel.ai_service == ai_service)
    if status:
        q = q.filter(LLMTraceModel.status == status)
    if date_from:
        q = q.filter(LLMTraceModel.created_at >= _parse_date(date_from))
    if date_to:
        q = q.filter(LLMTraceModel.created_at <= _parse_date(date_to, end_of_day=True))

    total = q.count()
    items = (
        q.order_by(LLMTraceModel.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_trace_to_dict(t) for t in items],
    }


def get_trace(db: Session, trace_id: str) -> Optional[Dict[str, Any]]:
    trace = db.query(LLMTraceModel).filter(LLMTraceModel.id == _safe_uuid(trace_id)).first()
    if not trace:
        return None
    return _trace_to_dict(trace, include_full_text=True)


# ─── Analytics ────────────────────────────────────────────────────────────────

def get_usage_analytics(
    db: Session,
    project_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """Return aggregated token/cost metrics for the analytics dashboard."""
    q = db.query(LLMTraceModel)

    if project_id:
        q = q.filter(LLMTraceModel.project_id == _safe_uuid(project_id))
    if date_from:
        q = q.filter(LLMTraceModel.created_at >= _parse_date(date_from))
    if date_to:
        q = q.filter(LLMTraceModel.created_at <= _parse_date(date_to, end_of_day=True))

    # Aggregate summary
    summary = db.query(
        func.count(LLMTraceModel.id).label("total_calls"),
        func.sum(LLMTraceModel.total_tokens).label("total_tokens"),
        func.sum(LLMTraceModel.prompt_tokens).label("total_prompt_tokens"),
        func.sum(LLMTraceModel.completion_tokens).label("total_completion_tokens"),
        func.sum(LLMTraceModel.estimated_cost_usd).label("total_cost_usd"),
        func.avg(LLMTraceModel.latency_ms).label("avg_latency_ms"),
        func.count(LLMTraceModel.id).filter(LLMTraceModel.status == "error").label("error_count"),
    ).filter(
        *_build_base_filters(LLMTraceModel, project_id, date_from, date_to)
    ).first()

    # Build a reusable WHERE clause + params dict to avoid mixed SQLAlchemy/psycopg2 issues
    where_parts = []
    params: Dict[str, Any] = {}
    if project_id:
        where_parts.append("project_id = %(pid)s::uuid")
        params["pid"] = project_id
    if date_from:
        where_parts.append("created_at >= %(df)s::timestamptz")
        params["df"] = date_from
    if date_to:
        where_parts.append("created_at <= %(dt)s::timestamptz")
        params["dt"] = date_to
    where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

    # Daily token trend
    daily_trend = db.execute(
        text(f"""
            SELECT
                DATE(created_at AT TIME ZONE 'UTC') AS day,
                ai_service,
                SUM(total_tokens)::bigint AS tokens,
                SUM(estimated_cost_usd)::numeric AS cost_usd,
                COUNT(*)::int AS calls
            FROM llm_trace
            {where_sql}
            GROUP BY day, ai_service
            ORDER BY day DESC
            LIMIT 300
        """),
        params,
    ).mappings().all()

    # Service breakdown
    service_breakdown = db.execute(
        text(f"""
            SELECT
                ai_service,
                COUNT(*)::int AS calls,
                SUM(total_tokens)::bigint AS tokens,
                SUM(estimated_cost_usd)::numeric AS cost_usd,
                ROUND(AVG(latency_ms))::int AS avg_latency_ms,
                COUNT(*) FILTER (WHERE status = 'error')::int AS errors
            FROM llm_trace
            {where_sql}
            GROUP BY ai_service
            ORDER BY cost_usd DESC
        """),
        params,
    ).mappings().all()

    # Model breakdown
    model_breakdown = db.execute(
        text(f"""
            SELECT
                model_name,
                llm_provider,
                COUNT(*)::int AS calls,
                SUM(total_tokens)::bigint AS tokens,
                SUM(estimated_cost_usd)::numeric AS cost_usd
            FROM llm_trace
            {where_sql}
            GROUP BY model_name, llm_provider
            ORDER BY cost_usd DESC
        """),
        params,
    ).mappings().all()

    return {
        "summary": {
            "total_calls": int(summary.total_calls or 0),
            "total_tokens": int(summary.total_tokens or 0),
            "total_prompt_tokens": int(summary.total_prompt_tokens or 0),
            "total_completion_tokens": int(summary.total_completion_tokens or 0),
            "total_cost_usd": float(summary.total_cost_usd or 0),
            "avg_latency_ms": int(summary.avg_latency_ms or 0),
            "error_count": int(summary.error_count or 0),
            "error_rate": round(
                (int(summary.error_count or 0) / int(summary.total_calls or 1)) * 100, 2
            ),
        },
        "daily_trend": [dict(row) for row in daily_trend],
        "service_breakdown": [dict(row) for row in service_breakdown],
        "model_breakdown": [dict(row) for row in model_breakdown],
    }


# ─── Rollup Job ───────────────────────────────────────────────────────────────

def compute_daily_rollup(db: Session, target_date: Optional[date] = None) -> int:
    """Aggregate llm_trace into daily_usage_rollup for target_date (default: yesterday)."""
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    db.execute(
        text("""
            DELETE FROM daily_usage_rollup
            WHERE rollup_date = :target_date
        """),
        {"target_date": target_date},
    )

    db.execute(
        text("""
            INSERT INTO daily_usage_rollup (
                id, rollup_date, project_id, user_id, ai_service, model_name,
                total_calls, total_prompt_tokens, total_completion_tokens,
                total_cost_usd, error_count, avg_latency_ms, computed_at
            )
            SELECT
                gen_random_uuid(),
                :target_date::date,
                project_id,
                user_id,
                ai_service,
                model_name,
                COUNT(*)::int,
                COALESCE(SUM(prompt_tokens), 0)::bigint,
                COALESCE(SUM(completion_tokens), 0)::bigint,
                COALESCE(SUM(estimated_cost_usd), 0)::numeric,
                COUNT(*) FILTER (WHERE status = 'error')::int,
                ROUND(AVG(latency_ms))::int,
                NOW()
            FROM llm_trace
            WHERE DATE(created_at AT TIME ZONE 'UTC') = :target_date::date
            GROUP BY project_id, user_id, ai_service, model_name
        """),
        {"target_date": target_date},
    )
    db.commit()

    count_row = db.execute(
        text("SELECT COUNT(*) FROM daily_usage_rollup WHERE rollup_date = :d"),
        {"d": target_date},
    ).scalar()
    return int(count_row or 0)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe_uuid(val: Any) -> Optional[UUID]:
    if val is None:
        return None
    try:
        return UUID(str(val))
    except (ValueError, AttributeError):
        return None


def _truncate(val: Any, max_len: int) -> Optional[str]:
    if val is None:
        return None
    s = str(val)
    if len(s) > max_len:
        return s[:max_len] + "…[truncated]"
    return s


def _parse_date(val: str, end_of_day: bool = False) -> datetime:
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if end_of_day and dt.hour == 0 and dt.minute == 0:
            dt = dt.replace(hour=23, minute=59, second=59)
        return dt
    except ValueError:
        d = datetime.strptime(val[:10], "%Y-%m-%d")
        if end_of_day:
            d = d.replace(hour=23, minute=59, second=59)
        return d


def _build_base_filters(model, project_id, date_from, date_to):
    filters = []
    if project_id:
        filters.append(model.project_id == _safe_uuid(project_id))
    if date_from:
        filters.append(model.created_at >= _parse_date(date_from))
    if date_to:
        filters.append(model.created_at <= _parse_date(date_to, end_of_day=True))
    return filters


def _trace_to_dict(trace: LLMTraceModel, include_full_text: bool = False) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": str(trace.id),
        "session_id": trace.session_id,
        "chart_id": str(trace.chart_id) if trace.chart_id else None,
        "project_id": str(trace.project_id) if trace.project_id else None,
        "user_id": str(trace.user_id) if trace.user_id else None,
        "ai_service": trace.ai_service,
        "llm_provider": trace.llm_provider,
        "model_name": trace.model_name,
        "prompt_tokens": trace.prompt_tokens,
        "completion_tokens": trace.completion_tokens,
        "total_tokens": trace.total_tokens,
        "estimated_cost_usd": float(trace.estimated_cost_usd or 0),
        "latency_ms": trace.latency_ms,
        "sql_generated": trace.sql_generated,
        "sql_retries": trace.sql_retries,
        "schema_tables_used": trace.schema_tables_used,
        "agent_steps": trace.agent_steps,
        "status": trace.status,
        "error_message": trace.error_message,
        "created_at": trace.created_at.isoformat() if trace.created_at else None,
    }
    if include_full_text:
        d["prompt_text"] = trace.prompt_text
        d["completion_text"] = trace.completion_text
    return d
