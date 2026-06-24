import io
import json
import logging
import os
import re
import time
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, HTTPException, UploadFile, status
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.configs.config import llm
from app.core.db import get_db
from app.models.schema_models import (
    DatabaseConnectionModel,
    OntologyEnrichmentSessionModel,
    OntologyVersionModel,
)
from app.utils.constants import Permissions as Permission
from app.utils.access import require_permission

logger = logging.getLogger(__name__)


def _safe_json_loads(value: Optional[str], fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _normalize_free_text(value: str) -> str:
    """
    Lightweight normalization for enrichment text answers.
    Handles common typos and sentence casing without hard failing.
    """
    if not value:
        return value

    text = " ".join(str(value).strip().split())
    if not text:
        return text

    typo_map = {
        "reenue": "revenue",
        "revnue": "revenue",
        "averge": "average",
        "avrage": "average",
        "defne": "define",
        "sumof": "sum of",
        "peryear": "per year",
    }

    tokens = text.split(" ")
    normalized_tokens = []
    for token in tokens:
        raw = token
        low = raw.lower()
        # preserve trailing punctuation
        punct = ""
        if low and low[-1] in {".", ",", ";", ":"}:
            punct = low[-1]
            low = low[:-1]
        rep = typo_map.get(low, low)
        normalized_tokens.append(rep + punct)

    text = " ".join(normalized_tokens)
    text = text[0].upper() + text[1:] if text else text
    if text and text[-1] not in {".", "!", "?"}:
        text += "."
    return text


import re


async def _llm_normalize_free_text(value: str, purpose: str) -> str:
    """
    Optional LLM-based text normalization for user enrichment answers.
    Falls back to heuristic normalization if endpoint is unavailable.
    """
    fallback = _normalize_free_text(value)
    endpoint = os.getenv("ONTOLOGY_TEXT_NORMALIZER_URL", "http://127.0.0.1:8001/api/ontology/normalize-text")
    timeout_seconds = float(os.getenv("ONTOLOGY_TEXT_NORMALIZER_TIMEOUT", "10"))
    payload = {
        "text": value,
        "purpose": purpose,
        "instructions": "Correct spelling and grammar only. Keep original meaning.",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
        normalized = data.get("text") if isinstance(data, dict) else None
        if isinstance(normalized, str) and normalized.strip():
            return _normalize_free_text(normalized.strip())
    except Exception:
        pass
    return fallback


# ---------------------------------------------------------------------------
# Typed Pydantic models for direct LangChain structured-output enrichment chat
# ---------------------------------------------------------------------------

class _MetricItem(BaseModel):
    """One metric row — use a list (not a dict keyed by name) so the LLM cannot emit {\"formula\": \"...\"} at the wrong level."""

    name: str = Field(
        description=(
            "Business name of the metric, e.g. 'Revenue per Customer' or 'Average Order Value'. "
            "Required on every metric row."
        )
    )
    description: str = Field(
        default="",
        description="Plain English description of what the metric measures.",
    )
    formula: str = Field(
        default="",
        description=(
            "SQL expression using ONLY real column names from schema_columns. "
            "Examples: SUM(price_after_discount)/COUNT(DISTINCT order_id), AVG(payment_value). "
            "NEVER use human-readable labels as the formula. "
            "Leave empty when status is 'pending' (awaiting user clarification)."
        ),
    )
    status: str = Field(
        default="active",
        description="'pending' when awaiting clarification; 'active' when formula is set.",
    )


class _EnrichmentChatOutput(BaseModel):
    assistant_message: str = Field(
        description=(
            "Short, friendly reply in plain English. "
            "When clarifying: list column options as a numbered list using readable labels. "
            "When confirming: acknowledge what was captured — no SQL or column names shown. "
            "When greeting: welcome and invite the user to share metrics."
        )
    )
    needs_clarification: bool = Field(
        default=False,
        description=(
            "True ONLY when the user's metric description is ambiguous and "
            "multiple columns/tables could match. Ask which one they mean."
        ),
    )
    metrics: List[_MetricItem] = Field(
        default_factory=list,
        description=(
            "Array of metrics. Each object MUST include: name, description, formula, status. "
            "Example: [{\"name\": \"Revenue per Customer\", \"description\": \"...\", "
            "\"formula\": \"SUM(price)/COUNT(DISTINCT customer_id)\", \"status\": \"active\"}]. "
            "When needs_clarification=true, set formula to \"\" and status to \"pending\". "
            "Do NOT put formula at the top level of metrics — only inside each array element."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _coerce_metrics_shape(cls, data: Any) -> Any:
        """LLMs often return metrics as {\"formula\": \"SQL\"} or {MetricName: {...}} instead of a list."""
        if not isinstance(data, dict):
            return data
        raw = data.get("metrics")
        if raw is None:
            return data
        if isinstance(raw, list):
            return data
        if not isinstance(raw, dict):
            return data

        # Wrong shape: keys are field names (formula, description, status) not metric names
        if ("formula" in raw or "description" in raw or "status" in raw) and not any(
            isinstance(v, dict) for v in raw.values()
        ):
            name = raw.get("name") or raw.get("metric_name") or "Metric"
            return {
                **data,
                "metrics": [
                    {
                        "name": str(name),
                        "description": str(raw.get("description", "")),
                        "formula": str(raw.get("formula", "")),
                        "status": str(raw.get("status", "active")),
                    }
                ],
            }

        # Dict keyed by metric name: {"Revenue per Customer": {"formula": "...", ...}}
        out: List[Dict[str, Any]] = []
        for key, val in raw.items():
            if isinstance(val, dict):
                out.append(
                    {
                        "name": str(val.get("name") or key),
                        "description": str(val.get("description", "")),
                        "formula": str(val.get("formula", "")),
                        "status": str(val.get("status", "active")),
                    }
                )
            elif isinstance(val, str):
                # e.g. {"Revenue": "SUM(...)"}  — treat value as formula
                out.append(
                    {
                        "name": str(key),
                        "description": "",
                        "formula": val,
                        "status": "active",
                    }
                )
        return {**data, "metrics": out}
    time_granularity: str = Field(
        default="",
        description=(
            "If the user specifies a reporting period: one of day | week | month | quarter | year. "
            "Empty string if not mentioned."
        ),
    )
    time_dimension: str = Field(
        default="",
        description=(
            "Actual column name from schema_columns the user wants to use as the date axis. "
            "Empty string if not mentioned."
        ),
    )
    status_values: List[str] = Field(
        default_factory=list,
        description="Success/active status values if the user defines them (e.g. ['delivered']).",
    )
    aliases: List[Dict[str, str]] = Field(
        default_factory=list,
        description=(
            "Term-to-column mappings. Each item: {\"term\": \"Revenue\", \"maps_to\": \"price_after_discount\"}."
        ),
    )


_ENRICHMENT_SYSTEM_PROMPT = """\
You are an ontology enrichment assistant for a NL2SQL system.
Your job is to extract business metric definitions and rules, then store them as
SQL formulas using ONLY real column names found in schema_columns.

══════════════════════════════════════════════════
GREETINGS / SMALL TALK
══════════════════════════════════════════════════
If the user sends only a greeting (hi, hello, thanks) with no business content:
- Set needs_clarification=false, metrics=[], all other fields empty/default.
- Reply warmly and invite them to share business metrics or rules.
- NEVER say "I captured that" when nothing was captured.

══════════════════════════════════════════════════
METRIC FORMULA — CRITICAL RULE
══════════════════════════════════════════════════
The `formula` field MUST always be a valid SQL expression.

COLUMN FORMAT: ALWAYS use the `use_in_formula` value from schema_columns (table.column).
  ✓ CORRECT:  SUM(order_header.price_after_discount) / COUNT(DISTINCT order_header.customer_id)
  ✓ CORRECT:  AVG(order_items.payment_value)
  ✓ CORRECT:  SUM(order_items.price) / COUNT(DISTINCT orders.order_id)
  ✗ WRONG:    SUM(price_after_discount)      ← bare column name, not safe in JOINs
  ✗ WRONG:    COUNT(DISTINCT order_id)       ← ambiguous if order_id exists in multiple tables
  ✗ WRONG:    Price After Discount / Number of Orders  ← plain English, not SQL

SQL formula guide (always use table.column format):
  "total X"         → SUM(table.col_name)
  "average X"       → AVG(table.col_name) or SUM(t.x)/COUNT(t.y)
  "number of Y"     → COUNT(DISTINCT table.y_id_column)
  "per customer"    → divide by COUNT(DISTINCT table.customer_id_column)
  "per order"       → divide by COUNT(DISTINCT table.order_id_column)

══════════════════════════════════════════════════
DIVISION SAFETY — MANDATORY FOR ALL DIALECTS
══════════════════════════════════════════════════
Whenever a formula divides by a column or expression that could be zero,
you MUST protect the denominator using ANSI-standard NULLIF:

  numerator / NULLIF(denominator, 0)
  AVG(numerator / NULLIF(denominator, 0))

This applies to PostgreSQL, MySQL, SQL Server, Oracle, and all dialects
UNLESS the SQL DIALECT section below explicitly says otherwise.

IMPORTANT — FORBIDDEN FUNCTIONS (unless the dialect section says to use them):
  ✗ NEVER use try_divide()  — this is Databricks-only and will ERROR on PostgreSQL/MySQL/Oracle
  ✗ NEVER use SAFE_DIVIDE() — this is BigQuery-only
  ✗ NEVER use IFF()         — use CASE WHEN ... THEN ... ELSE ... END instead
  ✗ NEVER use NVL()         — use COALESCE() instead (unless Oracle dialect is specified)

  ✓ STANDARD (works everywhere): numerator / NULLIF(denominator, 0)
  ✓ STANDARD: AVG(col_a / NULLIF(col_b, 0))
  ✗ WRONG (Databricks-only): try_divide(col_a, col_b)

- Dividing by COUNT(DISTINCT ...) inside a GROUP BY is safe (never zero).
- Dividing by a numeric literal (e.g. / 100, / 3600.0) is also safe.
- Any direct column-to-column division MUST use the safe NULLIF form above.

NOTE: Databricks-specific functions (try_divide, try_to_timestamp, etc.) are
described ONLY in the Databricks dialect section below. Do NOT use them for
any other database type.

══════════════════════════════════════════════════
CASES — read in order, use the FIRST that matches
══════════════════════════════════════════════════
CASE A — User gives an explicit SQL formula:
  Example: "Revenue per Order = SUM(price_after_discount) / COUNT(DISTINCT order_id)"
  Action: Preserve formula verbatim. needs_clarification=false.
  assistant_message: one sentence confirming what was saved, in plain English.
  Good examples:
    "Got it! I've saved Revenue per Order as the total revenue divided by the number of orders."
    "Saved! Approval Lead Time Hours has been captured as the time between order approval and purchase."
  NEVER say "Just a moment!", "I'll use...", "One second!", or any future/mid-process phrase.

CASE E — User defines the metric WITH an explicit arithmetic description (HIGHEST PRIORITY
          after CASE A — check this BEFORE looking at column ambiguity):
  Pattern: "<Name> is/equals/means <arithmetic expression using business terms>"
  Examples:
    "Total Revenue is 3 times the number of orders per year"
    "Average Order Value is total sales divided by number of orders"
    "Net Revenue is total sales minus total discounts"
    "Projected Revenue is current revenue times 1.25"
    "Conversion Rate is signups divided by total visitors"
  Rules:
  - Use the DEFINITION (the part after "is"/"equals"), NOT the metric name, to pick columns.
  - Map each business term in the definition to real schema columns:
      "number of orders" / "order count"        → COUNT(DISTINCT <order_id_col>)
      "total sales" / "total revenue"            → SUM(<revenue_col>)
      "total discounts" / "discount amount"      → SUM(<discount_col>)
      "number of customers" / "unique customers" → COUNT(DISTINCT <customer_id_col>)
  - Arithmetic words: "times"/"multiplied by" → *,  "divided by" → /,
                      "minus"/"less" → -,  "plus"/"added to" → +
  - "N times X" → (SQL for X) * N  e.g. "3 times orders" → COUNT(DISTINCT order_id) * 3
  - CLARIFICATION RULE: still ask a follow-up if a specific TERM in the definition maps
    to multiple columns. Ask about the TERM from the definition — NOT the metric name.
    WRONG question: "which column is your Total Revenue?"  ← about the metric name
    RIGHT question:  "which column represents 'number of orders'?" ← about the definition term
    Format: "To calculate <MetricName> as <plain description>, which column represents
             '<ambiguous term>'?
             1. <Label> (<Table>)
             2. <Label> (<Table>)
             Just reply with the number!"
  - needs_clarification=true when ANY definition term maps to multiple columns.
  - needs_clarification=false only when EVERY term maps to exactly ONE column.
  - When resolved (needs_clarification=false): assistant_message confirms in plain English.
    Good example: "Saved! I've captured Average Order Value as total sales divided by the
    number of orders."
  - metrics: one object, status="active" when formula resolved, "pending" while waiting.

CASE B — Natural language metric name with NO formula definition + ONE clear column match:
  Example: "Average Order Value" (no definition given, schema has one clear order-value col)
  Action: Derive SQL formula. needs_clarification=false.
  assistant_message: confirm what was saved in friendly plain English (no SQL shown).
  Good example: "Saved! I've captured Average Revenue using the Price After Discount field."
  metrics: one object, formula (SQL), status="active".

CASE C — Natural language metric name with NO formula definition + MULTIPLE column candidates:
  Example: "Total Revenue" (no definition, schema has price_after_discount AND payment_value)
  IMPORTANT: Only reach CASE C when the user has NOT defined how to calculate the metric.
             If the user said "X is Y times Z" — that is CASE E, not CASE C.
  needs_clarification=true.
  metrics: one object, formula="", status="pending".
  assistant_message: list ONLY the ambiguous term's options as a numbered list with
  READABLE LABELS (price_after_discount → "Price After Discount").
  Example:
    "To calculate Total Revenue I found a few options — which one should I use?
     1. Price After Discount (Order Header)
     2. Payment Value (Payments)
    Just reply with the number!"
  NEVER show raw column names to the user.

CASE D — User answers a previous clarification question:
  Examples: "1",  "the second one",  "price after discount",  "use payment value"
  Action: Map answer back to the real column. Build the SQL formula. needs_clarification=false.
  assistant_message: past-tense confirmation in friendly plain English. No SQL, no column names.
  Good example: "Got it! I've saved Revenue per Order using the Price After Discount field."
  metrics: YOU MUST include one object with ALL four fields:
    - name: EXACTLY the same metric name from the clarification question.
            NEVER use "Metric". NEVER leave it blank.
    - description: same plain-English description as the pending metric.
    - formula: the resolved SQL expression.
    - status: "active"

══════════════════════════════════════════════════
OTHER EXTRACTION RULES
══════════════════════════════════════════════════
- TIME GRANULARITY ("weekly", "monthly"): set time_granularity = "week" | "month" | etc.
- DATE COLUMN ("use order_date for trends"): set time_dimension = actual_column_name.
- STATUS VALUES ("delivered = success"): set status_values = ["delivered"].
- ALIASES ("Revenue means price_after_discount"): set aliases = [{"term": "Revenue", "maps_to": "price_after_discount"}].

══════════════════════════════════════════════════
HARD CONSTRAINTS
══════════════════════════════════════════════════
- formula must be SQL — never plain English labels.
- Never invent column names not in schema_columns.
- assistant_message is always plain English — never expose SQL, column names, or table names.
- assistant_message must ALWAYS be a complete, past-tense confirmation OR a specific question.
  FORBIDDEN phrases: "Just a moment!", "One second!", "I'll use...", "Let me...",
  "Please hold", "I'm calculating...", "Give me a moment", "I'll figure out...",
  "I'll apply...", "Working on it", or any future/present-progressive phrasing.
  When a metric is saved: use past tense — "I've saved", "I've captured", "Got it! Saved."
  When asking a question: end with "?" and give numbered options if applicable.
"""


# ---------------------------------------------------------------------------
# Per-database-type SQL dialect instructions injected into the formula prompt.
# Supported db_type values passed from the frontend:
#   postgres | mysql | databricks | oracledb | salesforce
# Update the entries here to adjust dialect guidance without touching the
# rest of the enrichment pipeline.
# ---------------------------------------------------------------------------
DB_TYPE_FORMULA_INSTRUCTIONS: Dict[str, str] = {
    "postgres": (
        "DATABASE DIALECT: PostgreSQL\n"
        "- Use DATE_TRUNC('month', col) / DATE_TRUNC('week', col) for time bucketing.\n"
        "- Use EXTRACT(EPOCH FROM col) for numeric timestamp arithmetic.\n"
        "- Prefer ::DATE / ::TIMESTAMP casts (e.g. col::DATE) over CAST(col AS DATE).\n"
        "- ILIKE is available for case-insensitive pattern matching.\n"
        "- Window functions (ROW_NUMBER() OVER (...)) are fully supported.\n"
        "- Use FILTER (WHERE ...) on aggregates when filtering within an aggregate is needed.\n"
        "- CURRENT_DATE and NOW() are valid date/time literals.\n"
        "- String concat: use || operator or CONCAT().\n"
        "- COALESCE, NULLIF, GREATEST, LEAST are all available.\n"
    ),
    "mysql": (
        "DATABASE DIALECT: MySQL\n"
        "- Use DATE_FORMAT(col, '%Y-%m') for month bucketing; YEARWEEK(col) for ISO weeks.\n"
        "- Use UNIX_TIMESTAMP(col) for numeric timestamp arithmetic.\n"
        "- Use CAST(col AS DATE) / CAST(col AS DATETIME) for type casts; :: is NOT supported.\n"
        "- Use IFNULL(col, default) instead of COALESCE where only two args are needed.\n"
        "- Window functions require MySQL 8.0+; prefer simple GROUP BY aggregates if version is uncertain.\n"
        "- ILIKE is NOT supported; use LIKE with LOWER(col) for case-insensitive matching.\n"
        "- String concat: use CONCAT() function — do NOT use the || operator.\n"
        "- CURDATE() is the equivalent of CURRENT_DATE.\n"
        "- GROUP_CONCAT is available for aggregating strings.\n"
        "- Backtick-quote reserved words in identifiers: `order`, `date`, `key`, etc.\n"
    ),
    "databricks": (
        "DATABASE DIALECT: Databricks SQL (Apache Spark SQL)\n"
        "- Use DATE_TRUNC('month', col) or TRUNC(col, 'MM') for time bucketing.\n"
        "- DATEDIFF(end_date, start_date) — argument order is end THEN start (opposite of MySQL).\n"
        "- Use TO_DATE(col) / TO_TIMESTAMP(col) for casting; :: syntax is NOT supported.\n"
        "- Backtick-quote column names that contain spaces or match reserved words: `my column`.\n"
        "- ILIKE is NOT supported; use LOWER(col) LIKE LOWER(pattern) for case-insensitive matching.\n"
        "- QUALIFY clause is supported for post-window-function filtering.\n"
        "- Use date_add(col, n) or DATEADD(unit, n, col) for date arithmetic.\n"
        "- CURRENT_DATE() and CURRENT_TIMESTAMP() require parentheses in Databricks SQL.\n"
        "- Never use PostgreSQL-specific syntax: no ::cast, no ILIKE, no FILTER on aggregates.\n"
        "- String concat: use CONCAT() or || (both are valid in Databricks SQL).\n"
        "- PIVOT / UNPIVOT are supported.\n"
        "- DIVISION SAFETY (CRITICAL): Databricks ANSI mode is ON by default — plain col / col "
        "raises DIVIDE_BY_ZERO when the denominator is 0. "
        "ALWAYS use try_divide(numerator, denominator) for any column-to-column division.\n"
        "  ✓ try_divide(op.payment_value, op.payment_installments)\n"
        "  ✓ AVG(try_divide(op.payment_value, op.payment_installments))\n"
        "  ✗ op.payment_value / op.payment_installments  ← WILL CRASH\n"
        "  ✗ AVG(op.payment_value / op.payment_installments)  ← WILL CRASH\n"
        "  Dividing by COUNT(DISTINCT ...) in a GROUP BY is safe; no try_divide needed there.\n"
        "- STRING DATE SAFETY (CRITICAL): Many columns store dates as STRING. "
        "Databricks ANSI mode raises CAST_INVALID_INPUT when malformed strings (e.g. free-text, "
        "'N/A') are implicitly cast to TIMESTAMP inside timestampdiff, datediff, or unix_timestamp. "
        "ALWAYS wrap date/timestamp column arguments in try_to_timestamp(col) when used in date "
        "arithmetic. try_to_timestamp() returns NULL for malformed rows — aggregates skip them safely.\n"
        "  ✓ timestampdiff(HOUR, try_to_timestamp(col_a), try_to_timestamp(col_b))\n"
        "  ✓ datediff(try_to_timestamp(end_col), try_to_timestamp(start_col))\n"
        "  ✗ timestampdiff(HOUR, col_a, col_b)  ← WILL throw CAST_INVALID_INPUT on dirty rows\n"
    ),
    "oracledb": (
        "DATABASE DIALECT: Oracle Database\n"
        "- Use TRUNC(col, 'MM') for month bucketing; TRUNC(col, 'IW') for ISO week.\n"
        "- Use TO_DATE(col, 'YYYY-MM-DD') / TO_TIMESTAMP for explicit type casts.\n"
        "- :: cast syntax is NOT supported; use CAST(col AS type) or TO_* conversion functions.\n"
        "- Use ROWNUM or ROW_NUMBER() OVER (...) for row limiting — LIMIT is NOT supported.\n"
        "- Use NVL(col, default) or COALESCE for null handling.\n"
        "- String concat: use || operator; CONCAT() only accepts exactly two arguments.\n"
        "- SYSDATE is Oracle's equivalent of CURRENT_DATE; SYSTIMESTAMP for full timestamps.\n"
        "- FROM DUAL is required for expressions with no real table (e.g. SELECT 1 FROM DUAL).\n"
        "- ILIKE is NOT supported; use UPPER(col) LIKE UPPER(pattern) for case-insensitive matching.\n"
        "- Use REGEXP_LIKE(col, pattern) for regular-expression matching.\n"
        "- Window functions are fully supported (Oracle 11g+).\n"
    ),
    "salesforce": (
        "DATABASE DIALECT: Salesforce SOQL (NOT standard SQL)\n"
        "- This is SOQL (Salesforce Object Query Language) — many standard SQL features do NOT apply.\n"
        "- Query structure: SELECT field1, field2 FROM SalesforceObject WHERE ... ORDER BY ... LIMIT n\n"
        "- Only one top-level object per query; cross-object data uses relationship traversal dot notation:\n"
        "  e.g. Account.Name referenced from an Opportunity query (parent) or\n"
        "       (SELECT Id FROM Contacts) as a sub-select (child relationship).\n"
        "- Aggregate functions available: COUNT(), COUNT(field), SUM(), AVG(), MIN(), MAX().\n"
        "  Aggregates require GROUP BY or must be the only SELECT expression.\n"
        "- Date/time: use SOQL date literals — TODAY, YESTERDAY, THIS_MONTH, LAST_N_DAYS:n,\n"
        "  THIS_YEAR, LAST_YEAR, THIS_QUARTER, LAST_QUARTER, etc. Do NOT use DATE_TRUNC.\n"
        "- Group by time period: use CALENDAR_MONTH(dateField), CALENDAR_YEAR(dateField),\n"
        "  CALENDAR_QUARTER(dateField), DAY_ONLY(dateField), HOUR_IN_DAY(dateField).\n"
        "- LIKE operator is case-insensitive by default in SOQL; ILIKE does NOT exist.\n"
        "- Always add WHERE IsDeleted = false unless explicitly including deleted records.\n"
        "- UNION, INTERSECT, and EXCEPT are NOT supported.\n"
        "- Sub-queries are supported only for semi-join/anti-join: WHERE Id IN (SELECT Id FROM ...).\n"
        "- Never use PostgreSQL, MySQL, or Databricks-specific functions (DATE_TRUNC, ILIKE, etc.).\n"
    ),
}

# Fallback instruction when db_type is unrecognised or not provided.
_DEFAULT_DB_TYPE_INSTRUCTION = (
    "DATABASE DIALECT: Generic SQL (db_type not specified)\n"
    "- Prefer ANSI SQL-92 standard syntax for maximum compatibility.\n"
    "- Avoid vendor-specific functions (e.g. DATE_TRUNC, ILIKE, ::cast).\n"
    "- Use CAST(col AS type) for all type conversions.\n"
    "- Use COALESCE for null handling.\n"
    "- Use standard aggregate functions: SUM, COUNT, AVG, MIN, MAX.\n"
    "- Use CURRENT_DATE / CURRENT_TIMESTAMP as date/time literals.\n"
)


def _get_db_type_sql_instructions(db_type: Optional[str]) -> str:
    """
    Return the SQL dialect instruction block to inject into the enrichment chat
    system prompt for the given db_type string.

    Supported values (as sent by the frontend):
        postgres | mysql | databricks | oracledb | salesforce
    """
    key = (db_type or "").strip().lower()
    # Normalise the one common alias used in the codebase.
    if key == "oracle":
        key = "oracledb"
    instructions = DB_TYPE_FORMULA_INSTRUCTIONS.get(key, _DEFAULT_DB_TYPE_INSTRUCTION)
    return (
        "══════════════════════════════════════════════════\n"
        "SQL DIALECT — CRITICAL: always follow these rules when writing metric formulas\n"
        "══════════════════════════════════════════════════\n"
        + instructions
    )


def _build_enrichment_schema_columns(
    ontology: Dict[str, Any],
    max_per_table: int = 25,
    max_tables: int = 40,
) -> Dict[str, list]:
    """Build a compact table_name → [{name, type}] mapping for the enrichment prompt."""
    id_to_table: Dict[str, str] = {}
    for cls in ontology.get("classes", []):
        if not isinstance(cls, dict):
            continue
        cid = str(cls.get("id") or "")
        table = (cls.get("table") or cls.get("name") or cid or "unknown").strip()
        if cid:
            id_to_table[cid] = table

    by_table: Dict[str, list] = {}
    for attr in ontology.get("attributes", []):
        if not isinstance(attr, dict):
            continue
        raw_cid = str(attr.get("class_id") or attr.get("class") or "unknown")
        table = id_to_table.get(raw_cid, raw_cid)
        col_name = attr.get("name") or ""
        col = {
            "name": col_name,
            "type": attr.get("type", "unknown"),
            # Qualified name hint so the LLM always writes table.column in formulas.
            "use_in_formula": f"{table}.{col_name}" if col_name else "",
        }
        by_table.setdefault(table, []).append(col)

    def _priority(c: dict) -> int:
        t = str(c.get("type", "")).upper()
        if any(k in t for k in ("INT", "FLOAT", "DECIMAL", "NUMERIC", "DOUBLE", "MONEY")):
            return 0
        if any(k in t for k in ("DATE", "TIME", "TIMESTAMP")):
            return 1
        return 2

    result: Dict[str, list] = {}
    for idx, (table, cols) in enumerate(by_table.items()):
        if idx >= max_tables:
            break
        result[table] = sorted(cols, key=_priority)[:max_per_table]
    return result


def _friendly_label(raw: str) -> str:
    if not raw:
        return "Field"
    text = str(raw).replace(".", " ").replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text.title() if text else "Field"


def _schema_column_index(schema_columns: Dict[str, list]) -> Dict[str, List[Tuple[str, str]]]:
    """
    Build a lowercase column-name index:
      column_name -> [(table_name, original_column_name), ...]
    """
    index: Dict[str, List[Tuple[str, str]]] = {}
    for table, cols in (schema_columns or {}).items():
        if not isinstance(cols, list):
            continue
        for col in cols:
            if not isinstance(col, dict):
                continue
            name = str(col.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            index.setdefault(key, []).append((str(table), name))
    return index


def _customer_identifier_candidates(schema_columns: Dict[str, list]) -> List[Tuple[str, str]]:
    """
    Find likely columns that can represent a unique customer key.
    Returns unique pairs of (table_name, column_name).
    """
    entity_terms = {"customer", "client", "buyer", "shopper", "user", "account", "member", "subscriber"}
    id_terms = {"id", "key", "uuid", "guid", "code", "number", "no"}
    found: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()
    for table, cols in (schema_columns or {}).items():
        if not isinstance(cols, list):
            continue
        for col in cols:
            if not isinstance(col, dict):
                continue
            name = str(col.get("name") or "").strip()
            if not name:
                continue
            words = set(_split_words(name))
            has_entity = bool(words & entity_terms)
            has_id = bool(words & id_terms) or name.lower().endswith("_id")
            if not (has_entity and has_id):
                continue
            pair = (str(table), name)
            if pair in seen:
                continue
            seen.add(pair)
            found.append(pair)
    return found[:8]


def _mentions_customer_uniqueness(text: str) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(
        phrase in low
        for phrase in (
            "per customer",
            "per unique customer",
            "unique customer",
            "distinct customer",
            "customer count",
        )
    )


def _chat_mentions_customer_uniqueness(chat_history: List[Dict[str, str]]) -> bool:
    for msg in chat_history or []:
        content = str((msg or {}).get("content") or "")
        if _mentions_customer_uniqueness(content):
            return True
    return False


def _looks_like_numeric_choice(text: str) -> bool:
    return bool(re.match(r"^\s*\d+\s*[\.\)]?.*$", text or ""))


def _last_assistant_requested_customer_identifier(chat_history: List[Dict[str, str]]) -> bool:
    for msg in reversed(chat_history or []):
        if str((msg or {}).get("role") or "").lower() != "assistant":
            continue
        content = str((msg or {}).get("content") or "").lower()
        if (
            "which column should represent a unique customer" in content
            or "which one should represent a unique customer" in content
            or "unique customer" in content
        ):
            return True
        return False
    return False


def _message_mentions_any_column(text: str, columns: Set[str]) -> bool:
    """
    True when user explicitly references a schema column token (snake_case style)
    in their message, which is treated as an intentional technical selection.
    """
    low = (text or "").lower()
    if not low:
        return False
    for col in columns:
        if col and re.search(rf"\b{re.escape(col)}\b", low):
            return True
    return False


def _build_customer_clarification_message(metric_name: str, candidates: List[Tuple[str, str]]) -> str:
    metric_label = metric_name or "this metric"
    if not candidates:
        return (
            f"To calculate {metric_label}, I still need one detail: which column should represent a unique customer? "
            "Please share the exact table and column."
        )

    lines = [
        f"To calculate {metric_label}, I still need one detail: which column should represent a unique customer?"
    ]
    for idx, (table, col) in enumerate(candidates, start=1):
        lines.append(f"{idx}. {_friendly_label(col)} ({_friendly_label(table)})")
    lines.append("Just reply with the number.")
    return "\n".join(lines)


def _normalize_label_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (text or "").lower())).strip()


def _resolve_customer_candidate_selection(
    user_message: str,
    candidates: List[Tuple[str, str]],
) -> Optional[str]:
    """
    Resolve user clarification answer to a concrete customer identifier column name.
    Supports numeric choices and label/table-text choices like:
      "2", "Customer Id (Order Header)", "customer_id"
    """
    if not candidates:
        return None

    msg = (user_message or "").strip()
    if not msg:
        return None

    num_match = re.match(r"^\s*(\d+)\s*[\.\)]?\s*$", msg)
    if num_match:
        idx = int(num_match.group(1)) - 1
        if 0 <= idx < len(candidates):
            return candidates[idx][1]

    msg_norm = _normalize_label_text(msg)
    for table, col in candidates:
        raw_col = (col or "").lower()
        if raw_col and re.search(rf"\b{re.escape(raw_col)}\b", msg.lower()):
            return col

        col_label = _normalize_label_text(_friendly_label(col))
        table_label = _normalize_label_text(_friendly_label(table))
        combined = f"{col_label} {table_label}".strip()
        if col_label and col_label in msg_norm:
            if table_label and table_label in msg_norm:
                return col
            # if user specified only column label and duplicates exist, keep scanning
            # for an exact table match first.
            fallback = col
            # If this label appears only once across candidates, accept immediately.
            dup_count = sum(
                1 for t2, c2 in candidates
                if _normalize_label_text(_friendly_label(c2)) == col_label
            )
            if dup_count == 1:
                return fallback
        if combined and combined in msg_norm:
            return col

    return None


def _qualify_formula_columns(
    formula: str,
    column_index: Dict[str, List[Tuple[str, str]]],
) -> str:
    """
    Replace bare column references in a SQL formula with table.column qualified names.

    Only qualifies when a column name maps to EXACTLY ONE table — if the same column
    name appears in multiple tables the reference is left as-is so the NL2SQL engine
    can decide, rather than silently picking the wrong table.

    Examples:
      "COUNT(DISTINCT order_id) * 3"
        order_id → only in order_header → "COUNT(DISTINCT order_header.order_id) * 3"

      "SUM(price) - SUM(discount)"
        price    → in order_items AND products → left bare (ambiguous)
        discount → only in order_items         → "SUM(order_items.discount)"
    """
    if not formula or not column_index:
        return formula

    def _replace(m: re.Match) -> str:
        ident = m.group(1)
        if ident.upper() in _SQL_RESERVED_TOKENS:
            return m.group(0)
        candidates = column_index.get(ident.lower(), [])
        if len(candidates) == 1:
            table, original_col = candidates[0]
            # Reconstruct with surrounding non-word chars preserved.
            return m.group(0).replace(ident, f"{table}.{original_col}", 1)
        return m.group(0)

    # Match bare word-boundary identifiers:
    #   - NOT already preceded by a dot  (already qualified: tbl.col)
    #   - NOT followed by an open-paren  (function call: SUM(), COUNT()…)
    return re.sub(
        r"(?<![.\w])([A-Za-z_][A-Za-z0-9_]*)(?!\s*\()(?![.\w])",
        _replace,
        formula,
    )


# ---------------------------------------------------------------------------
# Division-safety post-processor
# ---------------------------------------------------------------------------
# Matches bare column-to-column division: col / col  or  table.col / table.col
# Intentionally does NOT match aggregate-to-aggregate (SUM(x) / COUNT(y))
# because:
#   (a) the denominator patterns start with a function name followed by '(',
#       which is excluded by the right-boundary negative lookahead, and
#   (b) COUNT in a GROUP BY result set is guaranteed ≥ 1.
_UNSAFE_COL_DIV_RE = re.compile(
    r"(?<![.\w])"                                              # left word boundary
    r"((?:[A-Za-z_][A-Za-z0-9_]*\.)?[A-Za-z_][A-Za-z0-9_]*)"  # numerator col (bare or table.col)
    r"(?!\s*\()"                                               # numerator is NOT a function call
    r"(\s*/\s*)"                                               # division operator
    r"((?:[A-Za-z_][A-Za-z0-9_]*\.)?[A-Za-z_][A-Za-z0-9_]*)"  # denominator col (bare or table.col)
    r"(?!\s*[\(.\w])",                                         # denominator is NOT a function or further-qualified
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Per-dialect unsupported-function blocklists.
# Used by _validate_dialect_functions() and _rewrite_dialect_functions().
# Keys must match the normalised db_key values used throughout the pipeline.
# ---------------------------------------------------------------------------
_DIALECT_FORBIDDEN_FUNCTIONS: Dict[str, List[str]] = {
    # Functions that are Databricks-only and MUST NOT appear in other dialects.
    "postgres":  ["try_divide", "try_to_timestamp", "try_to_date", "safe_divide", "iff"],
    "mysql":     ["try_divide", "try_to_timestamp", "try_to_date", "safe_divide"],
    "oracledb":  ["try_divide", "try_to_timestamp", "try_to_date", "safe_divide", "isnull", "ifnull"],
    "mssql":     ["try_divide", "try_to_timestamp", "safe_divide", "nvl"],
    "salesforce": ["try_divide", "try_to_timestamp", "safe_divide", "nullif", "date_trunc", "ilike"],
    # databricks: no blocklist — all Spark-SQL functions are valid there.
}

# Rewrites: for non-Databricks dialects, replace known Databricks-only function
# calls with the ANSI-standard equivalent before the formula is persisted.
# Pattern: try_divide(numerator, denominator) → numerator / NULLIF(denominator, 0)
_TRY_DIVIDE_RE = re.compile(
    r"try_divide\s*\(\s*(.*?)\s*,\s*(.*?)\s*\)",
    re.IGNORECASE | re.DOTALL,
)
_SAFE_DIVIDE_RE = re.compile(
    r"safe_divide\s*\(\s*(.*?)\s*,\s*(.*?)\s*\)",
    re.IGNORECASE | re.DOTALL,
)


def _rewrite_dialect_functions(formula: str, db_type: Optional[str]) -> Tuple[str, bool]:
    """
    Rewrite dialect-incompatible function calls in a formula to their ANSI equivalents.

    For non-Databricks dialects:
      try_divide(x, y)  → x / NULLIF(y, 0)
      SAFE_DIVIDE(x, y) → x / NULLIF(y, 0)

    Returns (rewritten_formula, was_rewritten).
    """
    if not formula:
        return formula, False

    db_key = (db_type or "").strip().lower()
    if db_key == "oracle":
        db_key = "oracledb"

    # Databricks formulas are already correct — no rewrite needed.
    if db_key == "databricks":
        return formula, False

    original = formula
    # Replace try_divide(numerator, denominator) → numerator / NULLIF(denominator, 0)
    formula = _TRY_DIVIDE_RE.sub(lambda m: f"{m.group(1)} / NULLIF({m.group(2)}, 0)", formula)
    # Replace SAFE_DIVIDE(numerator, denominator) → numerator / NULLIF(denominator, 0)
    formula = _SAFE_DIVIDE_RE.sub(lambda m: f"{m.group(1)} / NULLIF({m.group(2)}, 0)", formula)

    was_rewritten = formula != original
    return formula, was_rewritten


def _validate_dialect_functions(
    formula: str,
    db_type: Optional[str],
    metric_name: str = "",
) -> List[str]:
    """
    Return a list of function names in *formula* that are forbidden for *db_type*.
    An empty list means the formula is dialect-compatible.
    """
    if not formula:
        return []
    db_key = (db_type or "").strip().lower()
    if db_key == "oracle":
        db_key = "oracledb"
    blocked = _DIALECT_FORBIDDEN_FUNCTIONS.get(db_key, [])
    found: List[str] = []
    for fn in blocked:
        # Match the function name followed by '(' with optional whitespace.
        if re.search(rf"\b{re.escape(fn)}\s*\(", formula, re.IGNORECASE):
            found.append(fn)
    if found:
        logger.warning(
            "[ONTOLOGY][DIALECT] Forbidden functions in metric '%s' for db_type='%s': %s | formula: %s",
            metric_name,
            db_type or "unknown",
            found,
            formula,
        )
    return found


def _make_division_safe(formula: str, db_type: Optional[str]) -> str:
    """
    Rewrite bare column-division patterns in a SQL metric formula to be safe
    against DIVIDE_BY_ZERO errors.

    For Databricks   → replaces `col / col` with `try_divide(col, col)`.
    For other DBs    → wraps the denominator with `NULLIF(col, 0)`.

    Only plain column references (optionally table-qualified) on both sides of
    the `/` are transformed.  Aggregate expressions such as `SUM(x) / COUNT(y)`
    are left untouched because the regex excludes identifiers that are followed
    by `(`.  Formulas already using `try_divide` or `NULLIF` are idempotent
    (the regex finds no matching bare `/`).

    Examples (Databricks):
      "op.payment_value / op.payment_installments"
        → "try_divide(op.payment_value, op.payment_installments)"
      "AVG(op.payment_value / op.payment_installments)"
        → "AVG(try_divide(op.payment_value, op.payment_installments))"

    Examples (PostgreSQL / MySQL / Oracle):
      "payment_value / payment_installments"
        → "payment_value / NULLIF(payment_installments, 0)"
      "AVG(payment_value / payment_installments)"
        → "AVG(payment_value / NULLIF(payment_installments, 0))"
    """
    if not formula:
        return formula

    db_key = (db_type or "").strip().lower()
    if db_key == "oracle":
        db_key = "oracledb"

    if db_key == "databricks":
        def _to_try_divide(m: re.Match) -> str:
            return f"try_divide({m.group(1)}, {m.group(3)})"
        return _UNSAFE_COL_DIV_RE.sub(_to_try_divide, formula)
    else:
        def _to_nullif(m: re.Match) -> str:
            return f"{m.group(1)}{m.group(2)}NULLIF({m.group(3)}, 0)"
        return _UNSAFE_COL_DIV_RE.sub(_to_nullif, formula)


def _infer_class_from_formula(
    formula: str,
    classes: List[Dict[str, Any]],
) -> Optional[str]:
    """
    Inspect a SQL formula for table.column references and return the class ID of the
    first table whose name (or table attribute) matches a table found in the formula.

    Returns None when no match can be made so callers can omit based_on_class rather
    than pointing to a random/wrong class.
    """
    if not formula or not classes:
        return None

    # Build a lookup: lowercase table-name (or class name) → class id.
    table_to_class: Dict[str, str] = {}
    for cls in classes:
        if not isinstance(cls, dict):
            continue
        cid = str(cls.get("id") or "").strip()
        if not cid:
            continue
        for key in ("table", "name"):
            val = str(cls.get(key) or "").strip()
            if val:
                table_to_class[val.lower()] = cid

    # Find all table.column patterns in the formula.
    for tbl, _col in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b", formula):
        cid = table_to_class.get(tbl.lower())
        if cid:
            return cid

    return None


def _enforce_customer_denominator(formula: str, customer_col: str) -> str:
    """
    Ensure formula denominator uses the selected customer column.
    """
    base = (formula or "").strip()
    if not base or not customer_col:
        return base
    target = f"COUNT(DISTINCT {customer_col})"
    # Collapse accidental duplicated denominator chains of the same selected column.
    target_chain_pattern = re.compile(
        rf"(\s*/\s*COUNT\s*\(\s*DISTINCT\s*{re.escape(customer_col)}\s*\))+",
        flags=re.IGNORECASE,
    )
    collapsed = target_chain_pattern.sub(f" / {target}", base)

    # If selected denominator already exists anywhere, keep it (idempotent).
    selected_exists_pattern = re.compile(
        rf"COUNT\s*\(\s*DISTINCT\s*{re.escape(customer_col)}\s*\)",
        flags=re.IGNORECASE,
    )
    if selected_exists_pattern.search(collapsed):
        return collapsed

    # Replace first COUNT(DISTINCT <any_col>) with selected one.
    any_count_distinct_pattern = re.compile(
        r"COUNT\s*\(\s*DISTINCT\s+[A-Za-z_\"`][A-Za-z0-9_\.\"`]*\s*\)",
        flags=re.IGNORECASE,
    )
    replaced = any_count_distinct_pattern.sub(target, collapsed, count=1)
    if replaced != collapsed:
        # Guard against accidental double append segments after replacement.
        replaced = re.sub(
            rf"(\s*/\s*{re.escape(target)}){{2,}}",
            f" / {target}",
            replaced,
            flags=re.IGNORECASE,
        )
        return replaced

    # No denominator found; append one exactly once.
    return f"{collapsed} / {target}"


async def _llm_enrichment_chat(
    ontology: Dict[str, Any],
    chat_history: List[Dict[str, str]],
    user_message: str,
    thread_id: Optional[str] = None,
    db_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Call OpenAI directly via LangChain with fully-typed structured output.
    Bypasses the LLM microservice httpx hop entirely — no intermediate timeout.
    Uses a typed Pydantic model (not Dict[str,Any]) so the LLM reliably fills every field.

    The system prompt is augmented with database-dialect–specific SQL instructions so
    the LLM generates formulas that are valid for the connected database type (e.g.
    Databricks vs PostgreSQL vs MySQL).
    """
    schema_columns = _build_enrichment_schema_columns(ontology)
    column_index = _schema_column_index(schema_columns)
    schema_column_names = set(column_index.keys())

    # Compose the system prompt: base instructions + dialect-specific SQL rules.
    dialect_instructions = _get_db_type_sql_instructions(db_type)
    system_prompt = _ENRICHMENT_SYSTEM_PROMPT + "\n" + dialect_instructions

    user_payload = json.dumps(
        {
            "db_type": db_type or "unknown",
            "schema_columns": schema_columns,
            "recent_chat_history": chat_history[-10:],
            "latest_user_message": user_message,
        },
        ensure_ascii=False,
    )
    try:
        # method="function_calling" avoids the strict additionalProperties constraint
        # imposed by json_schema mode on nested dicts.
        structured_llm = llm.with_structured_output(
            _EnrichmentChatOutput, method="function_calling"
        )
        result: _EnrichmentChatOutput = await structured_llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_payload),
            ]
        )

        assistant_message = (result.assistant_message or "").strip()
        needs_clarification = bool(result.needs_clarification)
        forced_clarification_message = ""

        # Hard guardrail: never allow hallucinated columns in metric formulas.
        for metric in result.metrics or []:
            formula = (metric.formula or "").strip()
            if not formula:
                continue
            identifiers = _extract_identifiers_from_formula(formula)
            missing = sorted(i for i in identifiers if i not in schema_column_names)
            if not missing:
                continue
            metric.formula = ""
            metric.status = "pending"
            needs_clarification = True
            if any("customer" in m for m in missing):
                forced_clarification_message = _build_customer_clarification_message(
                    _friendly_label(metric.name),
                    _customer_identifier_candidates(schema_columns),
                )
                break
            lines = [
                f"I want to confirm one thing before saving {_friendly_label(metric.name)}.",
                "I could not find all the columns needed for this metric in the schema.",
            ]
            # Build a semantically-relevant candidate list instead of showing the
            # first N columns in iteration order (which is usually wrong).
            #
            # Priority 1: columns whose name shares word-tokens with any missing identifier
            #             (e.g. missing "order_approved" → match "order_approved_at").
            # Priority 2: date/timestamp columns — most unresolved formulas involve time arithmetic.
            # Priority 3: first available columns as a last-resort fallback.
            seen_pairs: Set[Tuple[str, str]] = set()
            candidates: List[Tuple[str, str]] = []

            def _add_candidate(tbl: str, col_name: str) -> None:
                pair = (tbl, col_name)
                if pair not in seen_pairs and len(candidates) < 6:
                    seen_pairs.add(pair)
                    candidates.append(pair)

            # --- Priority 1: name-token similarity to missing identifiers ---
            missing_tokens: Set[str] = set()
            for m_ident in missing:
                missing_tokens.update(re.split(r"[^a-z0-9]+", m_ident.lower()))
            missing_tokens.discard("")

            for table, cols in schema_columns.items():
                if not isinstance(cols, list):
                    continue
                for col in cols:
                    if not isinstance(col, dict):
                        continue
                    col_name = str(col.get("name") or "").strip()
                    if not col_name:
                        continue
                    col_tokens = set(re.split(r"[^a-z0-9]+", col_name.lower()))
                    if col_tokens & missing_tokens:
                        _add_candidate(str(table), col_name)

            # --- Priority 2: date/timestamp-type columns ---
            if len(candidates) < 3:
                for table, cols in schema_columns.items():
                    if not isinstance(cols, list):
                        continue
                    for col in cols:
                        if not isinstance(col, dict):
                            continue
                        col_name = str(col.get("name") or "").strip()
                        col_type = str(col.get("type") or "").upper()
                        if col_name and any(
                            k in col_type for k in ("DATE", "TIME", "TIMESTAMP")
                        ):
                            _add_candidate(str(table), col_name)

            # --- Priority 3: fill remaining slots from whatever columns exist ---
            if len(candidates) < 3:
                for table, cols in schema_columns.items():
                    if not isinstance(cols, list):
                        continue
                    for col in cols:
                        if isinstance(col, dict) and str(col.get("name") or "").strip():
                            _add_candidate(str(table), str(col.get("name")))

            if candidates:
                lines.append("Which column(s) did you mean? Please pick:")
                for idx, (table, col) in enumerate(candidates, start=1):
                    lines.append(f"{idx}. {_friendly_label(col)} ({_friendly_label(table)})")
                lines.append("Reply with the number, or type the column name directly.")
            else:
                lines.append("Please share the exact table and column name to use.")
            forced_clarification_message = "\n".join(lines)
            break

        # Hard guardrail: for 'per unique customer' style metrics, do not auto-guess denominator.
        customer_intent_in_context = (
            _mentions_customer_uniqueness(user_message)
            or _chat_mentions_customer_uniqueness(chat_history)
        )
        if not forced_clarification_message and customer_intent_in_context:
            customer_candidates = _customer_identifier_candidates(schema_columns)
            user_explicitly_named_customer_column = _message_mentions_any_column(
                user_message, {c.lower() for _, c in customer_candidates}
            )
            user_selected_number = _looks_like_numeric_choice(user_message)
            last_assistant_asked_customer = _last_assistant_requested_customer_identifier(chat_history)
            selected_customer_column = _resolve_customer_candidate_selection(
                user_message, customer_candidates
            )
            for metric in result.metrics or []:
                formula = (metric.formula or "").strip()
                if not formula:
                    continue
                metric_text = f"{metric.name} {metric.description}".lower()
                metric_is_customer_based = (
                    "per customer" in metric_text
                    or "unique customer" in metric_text
                    or "distinct customer" in metric_text
                    or "customer" in metric_text
                )
                if not metric_is_customer_based and not _mentions_customer_uniqueness(formula):
                    continue
                formula_identifiers = _extract_identifiers_from_formula(formula)
                uses_customer_column = bool(
                    formula_identifiers & {c.lower() for _, c in customer_candidates}
                )
                denominator_confirmed = (
                    user_explicitly_named_customer_column
                    or bool(selected_customer_column)
                    or (
                        last_assistant_asked_customer
                        and user_selected_number
                        and uses_customer_column
                    )
                )
                if selected_customer_column:
                    metric.formula = _enforce_customer_denominator(formula, selected_customer_column)
                    formula_identifiers = _extract_identifiers_from_formula(metric.formula or "")
                    uses_customer_column = selected_customer_column.lower() in formula_identifiers
                if user_explicitly_named_customer_column and uses_customer_column:
                    continue
                needs_more_customer_clarification = (
                    (len(customer_candidates) > 1 and not denominator_confirmed)
                    or (not uses_customer_column and not denominator_confirmed)
                )
                if needs_more_customer_clarification:
                    metric.formula = ""
                    metric.status = "pending"
                    needs_clarification = True
                    forced_clarification_message = _build_customer_clarification_message(
                        _friendly_label(metric.name), customer_candidates
                    )
                    break

        # Build extracted_updates from the flat typed fields
        extracted_updates: Dict[str, Any] = {}

        if result.metrics:
            metrics_dict: Dict[str, Any] = {}
            for m in result.metrics:
                name = (m.name or "").strip()
                if not name or name == "Metric":
                    name = _recover_metric_name_from_chat(chat_history) or name or "Metric"
                entry: Dict[str, Any] = {}
                if m.description:
                    entry["description"] = m.description
                formula = (m.formula or "").strip()
                if formula:
                    raw_llm_formula = formula
                    # Step 1: Qualify bare column names → table.column so formulas are safe in JOINs.
                    formula = _qualify_formula_columns(formula, column_index)
                    # Step 2: Rewrite any Databricks-only function calls (e.g. try_divide) that
                    # the LLM incorrectly emitted for a non-Databricks dialect. This is the
                    # primary defence against the system-prompt bias described in the root-cause
                    # analysis: the global prompt's division-safety section used to show
                    # try_divide() examples, causing the LLM to use them for PostgreSQL too.
                    formula, was_rewritten = _rewrite_dialect_functions(formula, db_type)
                    if was_rewritten:
                        logger.warning(
                            "[ONTOLOGY][DIALECT] Rewrote dialect-incompatible functions in metric '%s' "
                            "(db_type=%r) | before=%r | after=%r",
                            name,
                            db_type or "unknown",
                            raw_llm_formula,
                            formula,
                        )
                    # Step 3: Guard against DIVIDE_BY_ZERO: rewrite bare col/col → NULLIF / try_divide.
                    formula = _make_division_safe(formula, db_type)
                    # Step 4: Validate that no forbidden dialect-specific functions remain.
                    forbidden = _validate_dialect_functions(formula, db_type, metric_name=name)
                    if forbidden:
                        logger.warning(
                            "[ONTOLOGY][DIALECT] Metric '%s' still contains forbidden functions %s "
                            "after all rewrites — formula will be cleared (db_type=%r).",
                            name,
                            forbidden,
                            db_type or "unknown",
                        )
                        formula = ""  # Clear invalid formula rather than persist garbage.
                    logger.info(
                        "[ONTOLOGY][DIALECT] Formula pipeline complete — metric='%s' db_type=%r "
                        "rewritten=%s forbidden=%s formula=%r",
                        name,
                        db_type or "unknown",
                        was_rewritten,
                        forbidden,
                        formula,
                    )
                    if formula:
                        entry["formula"] = formula
                        entry["status"] = "active"
                    else:
                        entry["status"] = "pending"
                else:
                    entry["status"] = "pending"
                metrics_dict[name] = entry
            if metrics_dict:
                extracted_updates["metrics"] = metrics_dict

        if needs_clarification and forced_clarification_message:
            assistant_message = forced_clarification_message

        if result.time_granularity:
            extracted_updates.setdefault("rules", {})["default_time_granularity"] = result.time_granularity
        if result.time_dimension:
            extracted_updates.setdefault("rules", {})["default_time_dimension"] = result.time_dimension
        if result.status_values:
            extracted_updates.setdefault("rules", {})["status_success_values"] = result.status_values
        if result.aliases:
            extracted_updates["aliases"] = result.aliases

        if not assistant_message:
            assistant_message = (
                "Could you clarify which column or table you mean?" if needs_clarification
                else "Got it! Feel free to share more metrics, rules, or date preferences."
            )

        # Post-LLM guardrail: replace incomplete/mid-process assistant messages.
        # The LLM occasionally generates future-tense or placeholder phrases
        # (e.g. "Just a moment!", "I'll use the appropriate expression...") when
        # CASE A / CASE E resolves without clarification.  Detect and replace them
        # so the user always sees a clear, past-tense confirmation.
        _INCOMPLETE_PHRASES = (
            "just a moment", "one second", "give me a moment", "hold on",
            "i'll use", "i'll apply", "i'll calculate", "i'll figure",
            "let me ", "working on it", "i'm calculating", "please hold",
            "i'll work", "i'll now", "i will use", "i will apply",
        )
        if not needs_clarification and any(
            p in assistant_message.lower() for p in _INCOMPLETE_PHRASES
        ):
            saved_metrics = [
                name
                for name, val in (extracted_updates.get("metrics") or {}).items()
                if isinstance(val, dict) and val.get("formula")
            ]
            if saved_metrics:
                label = _friendly_label(saved_metrics[0])
                assistant_message = (
                    f"Saved! I've captured **{label}** with the appropriate formula "
                    f"for your database. Feel free to add more metrics or rules!"
                )
            else:
                assistant_message = (
                    "Got it! Feel free to share more metrics, rules, or date preferences."
                )

        logger.info(
            "Enrichment chat | thread_id=%s | db_type=%s | needs_clarification=%s | updates_keys=%s",
            thread_id, db_type or "unknown", needs_clarification, list(extracted_updates.keys()),
        )
        return {
            "assistant_message": assistant_message,
            "extracted_updates": extracted_updates,
            "needs_clarification": needs_clarification,
        }

    except Exception as exc:
        logger.warning(
            "Enrichment chat fallback | thread_id=%s | error=%s", thread_id, str(exc)
        )
        return {
            "assistant_message": (
                "I'm here to help! Feel free to share your business metrics, "
                "reporting rules, or any date preferences you'd like to set up."
            ),
            "extracted_updates": {},
            "needs_clarification": False,
        }


async def _llm_apply_enrichment(
    ontology: Dict[str, Any],
    updates: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Ask LLM service to apply enrichment updates into ontology JSON.

    Only the semantic sections (metrics, rules, aliases, class names for context) are
    sent to the LLM — never the full schema with hundreds of attributes/relationships.
    This avoids LLM output-token limits and timeouts that occurred when sending the
    full ontology (~80-100 KB) and expecting an equally large response back.
    After the LLM returns the updated semantic sections, they are merged back into
    the full in-memory ontology before returning.
    """
    if not updates:
        # Nothing to apply — return the ontology unchanged (fast path).
        return ontology

    # ── Fast-path: skip the LLM call entirely when the only updates are metrics ──
    # Metrics are already converted to SQL formulas by the chat phase.  The LLM
    # apply step is only needed to semantically process rules/aliases.  If neither
    # is present we can inject metrics directly and avoid the 30-90s LLM round-trip.
    update_keys = {k for k, v in updates.items() if v}
    metrics_only = update_keys <= {"metrics"}
    if metrics_only:
        out = dict(ontology)
        if isinstance(updates.get("metrics"), dict):
            ont_classes: List[Dict[str, Any]] = [
                c for c in (out.get("classes") or []) if isinstance(c, dict)
            ]
            existing: List[Dict[str, Any]] = [
                m for m in (out.get("metrics") or []) if isinstance(m, dict)
            ]
            existing_names_lower = {str(m.get("name") or "").lower() for m in existing}
            for m_name, m_val in updates["metrics"].items():
                if not isinstance(m_val, dict):
                    continue
                formula = str(m_val.get("formula") or "").strip()
                if not formula:
                    continue
                inferred_class = _infer_class_from_formula(formula, ont_classes)
                new_entry: Dict[str, Any] = {
                    "id": f"metric:{m_name}",
                    "name": str(m_name),
                    "definition": str(m_val.get("description") or ""),
                    "formula": formula,
                    **({"based_on_class": inferred_class} if inferred_class else {}),
                }
                name_lower = m_name.lower()
                if name_lower in existing_names_lower:
                    for i, m in enumerate(existing):
                        if str(m.get("name") or "").lower() == name_lower:
                            existing[i] = {**m, **new_entry}
                            break
                else:
                    existing.append(new_entry)
            out["metrics"] = existing
        logger.info(
            "Enrichment apply fast-path (metrics-only, LLM skipped) | metrics_count=%d",
            len(updates.get("metrics") or {}),
        )
        return out

    endpoint = os.getenv("ONTOLOGY_ENRICHMENT_APPLY_URL", "http://127.0.0.1:8001/api/ontology/apply-enrichment")
    timeout_seconds = float(os.getenv("ONTOLOGY_ENRICHMENT_APPLY_TIMEOUT", "120"))

    # Build a compact payload — only what the LLM needs for semantic rules/alias merging.
    # Existing metrics are intentionally excluded: the chat phase already resolved all
    # formulas, and the post-LLM guarantee merge (below) injects any that the LLM misses.
    # class_names is capped to avoid bloating the context window on large schemas.
    _MAX_CLASS_NAMES = int(os.getenv("ONTOLOGY_APPLY_MAX_CLASS_NAMES", "30"))
    compact_ontology = {
        "rules": ontology.get("rules", {}),
        "aliases": ontology.get("aliases", []),
        "class_names": [
            {"id": c.get("id"), "name": c.get("name"), "table": c.get("table")}
            for c in ontology.get("classes", [])
            if isinstance(c, dict)
        ][:_MAX_CLASS_NAMES],
    }

    payload = {
        "ontology": compact_ontology,
        "updates": updates,
    }
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.post(endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()
        elapsed = round(time.perf_counter() - start, 3)
        logger.info(
            "LLM enrichment apply completed | elapsed_s=%s | endpoint=%s | updates_keys=%s",
            elapsed,
            endpoint,
            list((updates or {}).keys()),
        )
        enriched_compact = data.get("ontology") if isinstance(data, dict) else None
        if isinstance(enriched_compact, dict):
            # Merge the LLM-enriched semantic sections back into the full ontology.
            out = dict(ontology)
            if isinstance(enriched_compact.get("metrics"), list):
                out["metrics"] = enriched_compact["metrics"]
            if isinstance(enriched_compact.get("rules"), dict):
                out["rules"] = enriched_compact["rules"]
            if isinstance(enriched_compact.get("aliases"), list):
                out["aliases"] = enriched_compact["aliases"]
            # Guarantee: every update metric that has a formula must appear in the
            # final ontology. The LLM sometimes silently omits new metrics when it
            # cannot resolve column names (e.g. natural-language formulas with no
            # schema_columns in the payload). Direct-inject any that are missing.
            if isinstance(updates.get("metrics"), dict):
                existing_names_lower = {
                    str(m.get("name") or "").lower()
                    for m in (out.get("metrics") or [])
                    if isinstance(m, dict)
                }
                metrics_list = list(out.get("metrics") or [])
                ont_classes_llm: List[Dict[str, Any]] = [
                    c for c in (out.get("classes") or []) if isinstance(c, dict)
                ]
                for m_name, m_val in updates["metrics"].items():
                    if not isinstance(m_val, dict):
                        continue
                    formula = str(m_val.get("formula") or "").strip()
                    if not formula or m_name.lower() in existing_names_lower:
                        continue
                    logger.info(
                        "Post-LLM guarantee merge: injecting missing metric '%s' directly.", m_name
                    )
                    inferred_class_llm = _infer_class_from_formula(formula, ont_classes_llm)
                    metrics_list.append({
                        "id": f"metric:{m_name}",
                        "name": str(m_name),
                        "definition": str(m_val.get("description") or ""),
                        "formula": formula,
                        **({"based_on_class": inferred_class_llm} if inferred_class_llm else {}),
                    })
                out["metrics"] = metrics_list
            return out
    except Exception as exc:
        elapsed = round(time.perf_counter() - start, 3)
        logger.warning(
            "LLM enrichment apply failed | elapsed_s=%s | endpoint=%s | error=%s",
            elapsed,
            endpoint,
            str(exc),
        )
        out = dict(ontology)
        meta = out.setdefault("metadata", {}) if isinstance(out, dict) else {}
        if isinstance(meta, dict):
            meta["llm_enrichment_apply_error"] = True
            meta["llm_enrichment_apply_error_at"] = datetime.now(timezone.utc).isoformat()
            meta["llm_enrichment_apply_error_reason"] = str(exc)[:300]
        # Best-effort semantic merge so user changes are not lost on timeout/failure.
        # IMPORTANT: append/upsert into the existing metrics list — never replace it
        # wholesale, or all previously saved metrics would be wiped out.
        if isinstance(updates, dict):
            if isinstance(updates.get("metrics"), dict):
                ont_classes_fb: List[Dict[str, Any]] = [
                    c for c in (out.get("classes") or []) if isinstance(c, dict)
                ]
                existing: List[Dict[str, Any]] = [
                    m for m in (out.get("metrics") or []) if isinstance(m, dict)
                ]
                existing_names_lower = {str(m.get("name") or "").lower() for m in existing}
                for m_name, m_val in updates["metrics"].items():
                    if not isinstance(m_val, dict):
                        continue
                    formula = str(m_val.get("formula") or "").strip()
                    if not formula:
                        continue
                    inferred_class_fb = _infer_class_from_formula(formula, ont_classes_fb)
                    new_entry = {
                        "id": f"metric:{m_name}",
                        "name": str(m_name),
                        "definition": str(m_val.get("description") or ""),
                        "formula": formula,
                        **({"based_on_class": inferred_class_fb} if inferred_class_fb else {}),
                    }
                    name_lower = m_name.lower()
                    if name_lower in existing_names_lower:
                        # Update in-place so the formula is refreshed without duplicating.
                        for i, m in enumerate(existing):
                            if str(m.get("name") or "").lower() == name_lower:
                                existing[i] = {**m, **new_entry}
                                break
                    else:
                        existing.append(new_entry)
                out["metrics"] = existing
            if isinstance(updates.get("rules"), dict):
                rules = out.get("rules") if isinstance(out.get("rules"), dict) else {}
                rules.update(updates["rules"])
                out["rules"] = rules
            if isinstance(updates.get("aliases"), list):
                out["aliases"] = updates["aliases"]
        return out
    return ontology


def _iri_safe(raw: str) -> str:
    base = "".join(ch if ch.isalnum() else "_" for ch in (raw or "Thing"))
    return base.strip("_") or "Thing"


def _split_words(raw: str) -> List[str]:
    if not raw:
        return []
    # split snake_case, kebab-case, dots, camelCase
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(raw))
    s = re.sub(r"[^A-Za-z0-9]+", " ", s)
    return [w.lower() for w in s.split() if w]


def _to_class_name(raw: str) -> str:
    name = raw.split(".")[-1]
    clean = "".join(ch if ch.isalnum() else " " for ch in name)
    return "".join(part.capitalize() for part in clean.split()) or "Entity"


def _to_relation_label(source_column: str, target_table: str) -> str:
    """
    Generic relation naming from FK column and target entity.
    Avoids domain hardcoding (customer/seller/etc.).
    """
    words = _split_words(source_column)
    # Drop very common FK suffixes/prefixes for cleaner property names.
    stop = {"id", "pk", "fk", "key", "uuid", "guid", "ref", "code"}
    core = [w for w in words if w not in stop]
    if core:
        base = "".join(w.capitalize() for w in core)
        if base:
            return f"has{base}"
    return f"relatedTo{_to_class_name(target_table)}"


def _is_date_like(column_name: str, column_type: str) -> bool:
    words = _split_words(column_name)
    ctype = (column_type or "").lower()
    generic_terms = {"date", "time", "timestamp", "datetime", "created", "updated", "modified"}
    return bool(set(words) & generic_terms) or any(k in ctype for k in ["date", "time"])


def _is_revenue_like(column_name: str) -> bool:
    words = _split_words(column_name)
    generic_terms = {"revenue", "amount", "payment", "price", "total", "value", "cost", "sales", "income"}
    return bool(set(words) & generic_terms)


def _build_base_ontology(db_connection: DatabaseConnectionModel) -> Dict[str, Any]:
    ds_graph = _safe_json_loads(db_connection.ds_graph_json, {"nodes": [], "edges": [], "stats": {}})
    schema = _safe_json_loads(db_connection.db_schema, {"tables": []})

    class_nodes = []
    relationships = []
    attributes = []

    for node in ds_graph.get("nodes", []):
        class_name = _to_class_name(node.get("table") or node.get("label") or node.get("id"))
        class_nodes.append(
            {
                "id": node.get("id"),
                "name": class_name,
                "table": node.get("table") or node.get("label"),
                "schema": node.get("schema"),
                "column_count": node.get("column_count", 0),
            }
        )
        for col in node.get("columns", []):
            attributes.append(
                {
                    "class_id": node.get("id"),
                    "name": col.get("name"),
                    "type": col.get("type"),
                    "is_primary_key": bool(col.get("is_primary_key")),
                }
            )

    seen_pair_edges = set()
    for edge in ds_graph.get("edges", []):
        source = edge.get("source")
        target = edge.get("target")
        if not source or not target:
            continue
        pair_key = (source, target)
        if pair_key in seen_pair_edges:
            # Keep ontology graph clean: one semantic edge per table-pair for default view.
            continue
        seen_pair_edges.add(pair_key)
        relationships.append(
            {
                "id": edge.get("id"),
                "source": source,
                "target": target,
                "source_column": edge.get("source_column"),
                "target_column": edge.get("target_column"),
                "label": _to_relation_label(edge.get("source_column", ""), target),
                "relationship_type": edge.get("relationship_type", "foreign_key"),
            }
        )

    ontology = {
        "metadata": {
            "datasource_connection_id": str(db_connection.id),
            "db_type": db_connection.db_type,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "schema_table_count": len(schema.get("tables", [])),
        },
        "classes": class_nodes,
        "relationships": relationships,
        "attributes": attributes,
        "metrics": [],
        "aliases": [],
        "rules": {
            "default_filters": {},
            "default_time_dimension": None,
            "status_success_values": [],
        },
    }

    return ontology


def _merge_refined_with_canonical_mappings(
    canonical: Dict[str, Any],
    refined: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Keep technical schema mappings stable while allowing LLM-friendly business text.
    This prevents NL2SQL/graph regressions from accidental id/source/target rewrites.
    """
    if not isinstance(canonical, dict):
        return refined if isinstance(refined, dict) else {}
    if not isinstance(refined, dict):
        return canonical

    out = dict(canonical)
    out["metadata"] = refined.get("metadata", canonical.get("metadata", {})) if isinstance(refined.get("metadata"), dict) else canonical.get("metadata", {})
    out["rules"] = refined.get("rules", canonical.get("rules", {})) if isinstance(refined.get("rules"), dict) else canonical.get("rules", {})

    # For metrics: always prefer canonical (user-enriched) metrics over refined ones.
    # The refine LLM may strip or rename user-provided business formulas; the canonical
    # ontology is the authoritative source for metrics after enrichment.
    canonical_metrics = canonical.get("metrics", []) if isinstance(canonical.get("metrics"), list) else []
    refined_metrics = refined.get("metrics", []) if isinstance(refined.get("metrics"), list) else []
    if canonical_metrics:
        # Keep all canonical metrics; supplement with any net-new refined metrics.
        canonical_metric_names = {m.get("name") for m in canonical_metrics if isinstance(m, dict)}
        supplemental = [m for m in refined_metrics if isinstance(m, dict) and m.get("name") not in canonical_metric_names]
        out["metrics"] = canonical_metrics + supplemental
    else:
        out["metrics"] = refined_metrics

    out["aliases"] = refined.get("aliases", canonical.get("aliases", [])) if isinstance(refined.get("aliases"), list) else canonical.get("aliases", [])

    canonical_classes = canonical.get("classes", []) if isinstance(canonical.get("classes"), list) else []
    refined_class_by_id = {
        str(c.get("id")): c for c in (refined.get("classes", []) if isinstance(refined.get("classes"), list) else []) if isinstance(c, dict) and c.get("id")
    }
    merged_classes = []
    for c in canonical_classes:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id"))
        rc = refined_class_by_id.get(cid, {})
        merged = dict(c)
        if isinstance(rc.get("name"), str) and rc.get("name").strip():
            merged["name"] = rc["name"].strip()
        if isinstance(rc.get("description"), str) and rc.get("description").strip():
            merged["description"] = rc["description"].strip()
        merged_classes.append(merged)
    out["classes"] = merged_classes

    canonical_relationships = canonical.get("relationships", []) if isinstance(canonical.get("relationships"), list) else []
    refined_rel_by_id = {
        str(r.get("id")): r for r in (refined.get("relationships", []) if isinstance(refined.get("relationships"), list) else []) if isinstance(r, dict) and r.get("id")
    }
    merged_relationships = []
    for r in canonical_relationships:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id"))
        rr = refined_rel_by_id.get(rid, {})
        merged = dict(r)
        if isinstance(rr.get("label"), str) and rr.get("label").strip():
            merged["label"] = rr["label"].strip()
        if isinstance(rr.get("description"), str) and rr.get("description").strip():
            merged["description"] = rr["description"].strip()
        merged_relationships.append(merged)
    out["relationships"] = merged_relationships

    canonical_attributes = canonical.get("attributes", []) if isinstance(canonical.get("attributes"), list) else []
    refined_attrs = refined.get("attributes", []) if isinstance(refined.get("attributes"), list) else []
    refined_attr_by_key = {}
    for a in refined_attrs:
        if not isinstance(a, dict):
            continue
        key = f"{a.get('class_id')}::{a.get('name')}"
        refined_attr_by_key[key] = a
    merged_attributes = []
    for a in canonical_attributes:
        if not isinstance(a, dict):
            continue
        key = f"{a.get('class_id')}::{a.get('name')}"
        ra = refined_attr_by_key.get(key, {})
        merged = dict(a)
        if isinstance(ra.get("description"), str) and ra.get("description").strip():
            merged["description"] = ra["description"].strip()
        merged_attributes.append(merged)
    out["attributes"] = merged_attributes
    return out


async def _llm_refine_ontology(
    ontology: Dict[str, Any],
    db_schema_json: Optional[str],
    db_type: Optional[str],
    timeout_seconds: float = 20.0,
) -> Dict[str, Any]:
    """
    Optional LLM-assisted refinement.
    Fallback-safe: returns original ontology if LLM is unavailable or invalid.
    """
    llm_endpoint = os.getenv("ONTOLOGY_REFINER_URL", "http://127.0.0.1:8001/api/ontology/refine")
    timeout_seconds = float(os.getenv("ONTOLOGY_REFINER_TIMEOUT", str(timeout_seconds)))
    payload = {
        "db_type": db_type or "unknown",
        "db_schema": db_schema_json or "{}",
        "ontology": ontology,
        "instructions": (
            "Refine ontology names and relationship labels to business-friendly terms. "
            "Keep schema compatibility. Return JSON object only."
        ),
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(llm_endpoint, json=payload)
            response.raise_for_status()
            data = response.json()

        refined = data.get("ontology") if isinstance(data, dict) else None
        if not isinstance(refined, dict):
            return ontology

        # Minimal shape checks
        if not isinstance(refined.get("classes"), list) or not isinstance(refined.get("relationships"), list):
            return ontology

        refined.setdefault("metadata", {})
        refined["metadata"]["llm_refined"] = True
        refined["metadata"]["llm_refined_at"] = datetime.now(timezone.utc).isoformat()
        return refined
    except Exception as exc:
        logger.warning("LLM ontology refinement skipped: %s", str(exc))
        ontology.setdefault("metadata", {})
        ontology["metadata"]["llm_refined"] = False
        return ontology


def _ontology_to_graph(ontology: Dict[str, Any]) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    for cls in ontology.get("classes", []):
        if not isinstance(cls, dict):
            continue
        cls_id = cls.get("id") or cls.get("table") or "unknown"
        cls_name = cls.get("name") or cls.get("table") or str(cls_id)
        nodes.append(
            {
                "id": str(cls_id),
                "label": str(cls_name),
                "type": "class",
                "meta": {
                    "table": cls.get("table"),
                    "schema": cls.get("schema"),
                    "column_count": cls.get("column_count", 0),
                },
            }
        )

    for metric in ontology.get("metrics", []):
        if not isinstance(metric, dict):
            continue
        metric_id = metric.get("id") or f"metric:{metric.get('name', 'metric')}"
        nodes.append(
            {
                "id": str(metric_id),
                "label": metric.get("name", "Metric"),
                "type": "metric",
                "meta": {"definition": metric.get("definition"), "formula": metric.get("formula")},
            }
        )
        base_class = metric.get("based_on_class")
        if base_class:
            edges.append(
                {
                    "id": f"{metric_id}->{base_class}",
                    "source": str(metric_id),
                    "target": str(base_class),
                    "label": "based on",
                    "type": "metric_link",
                    "meta": {},
                }
            )

    for rel in ontology.get("relationships", []):
        if not isinstance(rel, dict):
            continue
        rel_id = rel.get("id") or f"{rel.get('source', 'src')}__{rel.get('target', 'tgt')}"
        rel_source = rel.get("source") or "unknown"
        rel_target = rel.get("target") or "unknown"
        edges.append(
            {
                "id": str(rel_id),
                "source": str(rel_source),
                "target": str(rel_target),
                "label": rel.get("label") or rel.get("relationship_type", "relation"),
                "type": rel.get("relationship_type", "foreign_key"),
                "meta": {
                    "source_column": rel.get("source_column"),
                    "target_column": rel.get("target_column"),
                },
            }
        )

    stats = {
        "class_count": len([n for n in nodes if n["type"] == "class"]),
        "metric_count": len([n for n in nodes if n["type"] == "metric"]),
        "relation_count": len(edges),
    }

    return {"nodes": nodes, "edges": edges, "stats": stats}


def _ontology_to_ttl(ontology: Dict[str, Any]) -> str:
    """
    Convert internal ontology JSON to Turtle.
    Uses rdflib when available, falls back to manual Turtle.
    """
    try:
        from rdflib import Graph, Namespace, RDF, RDFS, OWL, XSD, Literal, URIRef

        ex = Namespace("http://vizai.ai/ontology#")
        g = Graph()
        g.bind("ex", ex)
        g.bind("owl", OWL)
        g.bind("rdfs", RDFS)
        g.bind("xsd", XSD)

        class_map: Dict[str, URIRef] = {}
        for cls in ontology.get("classes", []):
            cid = cls.get("id", "")
            cname = _iri_safe(cls.get("name") or cls.get("table") or cid)
            c_uri = ex[cname]
            class_map[cid] = c_uri
            g.add((c_uri, RDF.type, OWL.Class))

        for rel in ontology.get("relationships", []):
            src = class_map.get(rel.get("source", ""), ex[_iri_safe(rel.get("source", "Source"))])
            tgt = class_map.get(rel.get("target", ""), ex[_iri_safe(rel.get("target", "Target"))])
            rel_id = str(rel.get("id") or "")
            rel_label = str(rel.get("label") or rel.get("relationship_type") or "relatedTo")
            # Keep each relationship as its own property in OWL to avoid domain/range collapsing
            # when multiple edges share the same label (e.g., many "hasItem" relations).
            prop_key = f"{_iri_safe(rel_label)}_{_iri_safe(rel_id)}" if rel_id else _iri_safe(rel_label)
            prop = ex[prop_key]
            g.add((prop, RDF.type, OWL.ObjectProperty))
            g.add((prop, RDFS.domain, src))
            g.add((prop, RDFS.range, tgt))
            g.add((prop, RDFS.label, Literal(rel_label)))

        for attr in ontology.get("attributes", []):
            src = class_map.get(attr.get("class_id", ""), ex[_iri_safe(attr.get("class_id", "Entity"))])
            prop = ex[_iri_safe(attr.get("name", "attribute"))]
            dtype_raw = str(attr.get("type", "")).lower()
            dtype = XSD.string
            if any(k in dtype_raw for k in ["int", "number"]):
                dtype = XSD.integer
            elif any(k in dtype_raw for k in ["float", "double", "decimal", "numeric"]):
                dtype = XSD.decimal
            elif any(k in dtype_raw for k in ["date", "time"]):
                dtype = XSD.dateTime
            g.add((prop, RDF.type, OWL.DatatypeProperty))
            g.add((prop, RDFS.domain, src))
            g.add((prop, RDFS.range, dtype))

        for metric in ontology.get("metrics", []):
            mid = ex[_iri_safe(metric.get("name", "Metric"))]
            g.add((mid, RDF.type, ex.BusinessMetric))
            if metric.get("definition"):
                g.add((mid, ex.definition, Literal(str(metric["definition"]))))
            if metric.get("formula"):
                g.add((mid, ex.formula, Literal(str(metric["formula"]))))

        return g.serialize(format="turtle")
    except Exception:
        # Fallback to manual Turtle if rdflib is unavailable.
        pass

    lines: List[str] = [
        "@prefix ex: <http://vizai.ai/ontology#> .",
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
    ]

    class_map: Dict[str, str] = {}
    for cls in ontology.get("classes", []):
        cid = cls.get("id", "")
        cname = _iri_safe(cls.get("name") or cls.get("table") or cid)
        class_map[cid] = cname
        lines.append(f"ex:{cname} a owl:Class .")

    lines.append("")

    for rel in ontology.get("relationships", []):
        src = class_map.get(rel.get("source", ""), _iri_safe(rel.get("source", "Source")))
        tgt = class_map.get(rel.get("target", ""), _iri_safe(rel.get("target", "Target")))
        rel_id = str(rel.get("id") or "")
        rel_label = str(rel.get("label") or rel.get("relationship_type") or "relatedTo")
        prop = f"{_iri_safe(rel_label)}_{_iri_safe(rel_id)}" if rel_id else _iri_safe(rel_label)
        safe_label = rel_label.replace('"', '\\"')
        lines.append(
            f'ex:{prop} a owl:ObjectProperty ; rdfs:domain ex:{src} ; rdfs:range ex:{tgt} ; rdfs:label "{safe_label}" .'
        )

    lines.append("")

    for attr in ontology.get("attributes", []):
        src = class_map.get(attr.get("class_id", ""), _iri_safe(attr.get("class_id", "Entity")))
        prop = _iri_safe(attr.get("name", "attribute"))
        dtype_raw = str(attr.get("type", "")).lower()
        dtype = "xsd:string"
        if any(k in dtype_raw for k in ["int", "number"]):
            dtype = "xsd:integer"
        elif any(k in dtype_raw for k in ["float", "double", "decimal", "numeric"]):
            dtype = "xsd:decimal"
        elif any(k in dtype_raw for k in ["date", "time"]):
            dtype = "xsd:dateTime"
        lines.append(f"ex:{prop} a owl:DatatypeProperty ; rdfs:domain ex:{src} ; rdfs:range {dtype} .")

    lines.append("")

    for metric in ontology.get("metrics", []):
        mid = _iri_safe(metric.get("name", "Metric"))
        definition = str(metric.get("definition", "")).replace('"', '\\"')
        formula = str(metric.get("formula", "")).replace('"', '\\"')
        lines.append(f"ex:{mid} a ex:BusinessMetric .")
        if definition:
            lines.append(f'ex:{mid} ex:definition "{definition}" .')
        if formula:
            lines.append(f'ex:{mid} ex:formula "{formula}" .')

    return "\n".join(lines)


def _extract_candidate_columns(ontology: Dict[str, Any]) -> Dict[str, List[str]]:
    date_candidates: List[str] = []
    revenue_candidates: List[str] = []
    status_candidates: List[str] = []

    for attr in ontology.get("attributes", []):
        name = attr.get("name", "")
        col_type = str(attr.get("type", ""))
        if _is_date_like(name, col_type):
            date_candidates.append(name)
        if _is_revenue_like(name):
            revenue_candidates.append(name)
        if "status" in name.lower() or "state" in name.lower():
            status_candidates.append(name)

    return {
        "date": sorted(set(date_candidates)),
        "revenue": sorted(set(revenue_candidates)),
        "status": sorted(set(status_candidates)),
    }


def _generate_dynamic_questions(ontology: Dict[str, Any], db_type: Optional[str]) -> List[Dict[str, Any]]:
    candidates = _extract_candidate_columns(ontology)
    questions: List[Dict[str, Any]] = []

    if len(candidates["date"]) > 1:
        questions.append(
            {
                "question_id": "default_date_dimension",
                "target_term": "rules.default_time_dimension",
                "question": "Which date/time column should be used by default for business trends?",
                "reason": "Multiple date-like columns were found.",
                "answer_type": "single_select",
                "options": candidates["date"][:8],
                "priority": 10,
            }
        )
        questions.append(
            {
                "question_id": "default_time_granularity",
                "target_term": "rules.default_time_granularity",
                "question": "What default time granularity should we use in trends?",
                "reason": "Choosing day/week/month improves consistent chart outputs.",
                "answer_type": "single_select",
                "options": ["day", "week", "month", "quarter"],
                "priority": 12,
            }
        )

    if len(candidates["revenue"]) > 0:
        questions.append(
            {
                "question_id": "average_revenue_formula",
                "target_term": "metrics.AverageRevenue",
                "question": "How should we define Average Revenue for this datasource?",
                "reason": "Revenue-like columns were detected; definition varies by business.",
                "answer_type": "text",
                "options": [],
                "priority": 20,
            }
        )
        questions.append(
            {
                "question_id": "average_revenue_denominator",
                "target_term": "metrics.AverageRevenue.denominator",
                "question": "Average revenue should be calculated per what unit?",
                "reason": "Different businesses define average revenue differently.",
                "answer_type": "single_select",
                "options": ["order", "customer", "product", "seller"],
                "priority": 22,
            }
        )

    if len(candidates["status"]) > 0:
        questions.append(
            {
                "question_id": "success_status_values",
                "target_term": "rules.status_success_values",
                "question": "Which status values should count as successful records?",
                "reason": "Status column(s) detected and this impacts business metrics.",
                "answer_type": "text",
                "options": [],
                "priority": 30,
            }
        )

    questions.append(
        {
            "question_id": "exclude_test_data",
            "target_term": "rules.default_filters",
            "question": "Do you want to exclude any test/internal data by default?",
            "reason": "Default quality filters improve query consistency.",
            "answer_type": "text",
            "options": [],
            "priority": 40,
        }
    )

    if (db_type or "").lower() == "salesforce":
        questions.append(
            {
                "question_id": "salesforce_deleted_filter",
                "target_term": "rules.default_filters.IsDeleted",
                "question": "Should records with IsDeleted=true be excluded by default?",
                "reason": "Salesforce objects commonly include soft-deleted records.",
                "answer_type": "single_select",
                "options": ["Yes", "No"],
                "priority": 15,
            }
        )

    return sorted(questions, key=lambda q: q.get("priority", 100))


async def _apply_answers_to_ontology(ontology: Dict[str, Any], answers: Dict[str, Any]) -> Dict[str, Any]:
    updated = await _llm_apply_enrichment(json.loads(json.dumps(ontology)), answers or {})
    updated.setdefault("metadata", {})["last_enriched_at"] = datetime.now(timezone.utc).isoformat()
    if isinstance(answers, dict):
        updated.setdefault("metadata", {})["last_enrichment_applied_keys"] = sorted(list(answers.keys()))
    return updated


# ---------------------------------------------------------------------------
# Metric formula validation against the actual database schema.
# Prevents users from saving business metrics like
#   SUM(payment_value) / COUNT(DISTINCT order_id)
# when `payment_value` does not exist in any real table. The NL2SQL agent
# (correctly) refuses to use such formulas, so saving them is misleading.
# ---------------------------------------------------------------------------

_SQL_RESERVED_TOKENS: Set[str] = {
    # aggregates / window
    "SUM", "COUNT", "AVG", "MAX", "MIN", "DISTINCT",
    "ROW_NUMBER", "RANK", "DENSE_RANK", "OVER", "PARTITION",
    "FIRST_VALUE", "LAST_VALUE", "LAG", "LEAD", "NTILE",
    "CUME_DIST", "PERCENT_RANK", "PERCENTILE_CONT", "PERCENTILE_DISC",
    "STDDEV", "STDDEV_POP", "STDDEV_SAMP", "VARIANCE", "VAR_POP", "VAR_SAMP",
    "MEDIAN", "ANY_VALUE", "BOOL_AND", "BOOL_OR",
    # control flow
    "CASE", "WHEN", "THEN", "ELSE", "END", "IIF",
    "AND", "OR", "NOT", "NULL", "IS", "IN", "BETWEEN", "LIKE", "ILIKE", "EXISTS",
    # clause/structural keywords
    "SELECT", "FROM", "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "OUTER", "CROSS", "ON",
    "WHERE", "GROUP", "BY", "HAVING", "ORDER", "DESC", "ASC", "LIMIT", "OFFSET",
    "AS", "UNION", "ALL", "INTERSECT", "EXCEPT", "WITH", "RECURSIVE",
    "LATERAL", "QUALIFY", "PIVOT", "UNPIVOT", "WITHIN",
    "ROLLUP", "CUBE", "GROUPING", "SETS", "TIES",
    # window frame keywords
    "ROWS", "RANGE", "UNBOUNDED", "PRECEDING", "FOLLOWING", "CURRENT",
    # standard SQL functions used in formulas
    "DATE_TRUNC", "EXTRACT", "TO_CHAR", "TO_DATE", "TO_TIMESTAMP",
    "CAST", "CONVERT", "SAFE_CAST", "TRY_CAST",
    "COALESCE", "NULLIF", "GREATEST", "LEAST", "NVL", "IFNULL", "ISNULL", "NVL2",
    "ROUND", "FLOOR", "CEIL", "CEILING", "ABS", "POWER", "SQRT", "SIGN",
    "MOD", "TRUNC", "EXP", "LN", "LOG",
    "LENGTH", "LEN", "LOWER", "UPPER", "TRIM", "LTRIM", "RTRIM",
    "CONCAT", "SUBSTRING", "SUBSTR", "LEFT", "RIGHT", "REPLACE", "SPLIT_PART",
    "CURRENT_DATE", "CURRENT_TIMESTAMP", "NOW", "SYSDATE", "GETDATE", "CURDATE",
    "REGEXP_LIKE", "REGEXP_REPLACE", "REGEXP_SUBSTR",
    "ARRAY_AGG", "STRING_AGG", "GROUP_CONCAT", "LISTAGG",
    "APPROX_COUNT_DISTINCT",
    # date/time arithmetic functions (cross-dialect) — the primary cause of false
    # "missing column" triggers when the LLM generates time-delta formulas.
    "DATEDIFF", "DATEADD", "DATE_ADD", "DATE_SUB", "DATE_DIFF",
    "TIMESTAMPDIFF", "TIMEDIFF", "TIMEDELTA",
    "DATEPART", "DATENAME", "DATETRUNC",
    "UNIX_TIMESTAMP", "FROM_UNIXTIME",
    "DATE_FORMAT", "STR_TO_DATE",
    "AGE", "JULIANDAY", "STRFTIME",
    "CALENDAR_MONTH", "CALENDAR_YEAR", "CALENDAR_QUARTER",
    "DAY_ONLY", "HOUR_IN_DAY",
    "INTERVAL",

    # Boolean literals
    "TRUE",
    "FALSE",
    
    # Null literal
    "NULL",
    # type names (in CAST expressions)
    "INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT", "TEXT", "VARCHAR", "CHAR",
    "DATE", "TIMESTAMP", "TIMESTAMPTZ", "DATETIME", "NUMERIC", "DECIMAL", "FLOAT",
    "DOUBLE", "REAL", "BOOLEAN", "BOOL", "NUMBER", "BINARY_FLOAT", "BINARY_DOUBLE",
    # time grain / unit keywords used inside DATE_TRUNC / EXTRACT / DATEDIFF
    "YEAR", "QUARTER", "MONTH", "WEEK", "DAY", "HOUR", "MINUTE", "SECOND",
    "EPOCH", "DOW", "DOY", "ISOYEAR", "ISOWEEK",
    # Databricks / Spark SQL dialect-specific functions.
    # Must be in this set so _extract_identifiers_from_formula treats them as
    # function calls (not column references) and never flags them as missing columns.
    "TRY_DIVIDE", "TRY_TO_TIMESTAMP", "TRY_TO_DATE", "TRY_TO_NUMBER",
    "SAFE_DIVIDE",  # BigQuery safe-division — not valid on other dialects
    "IFF",          # Snowflake / Databricks shorthand for CASE WHEN
    "DECODE",       # Oracle legacy conditional
    "LPAD", "RPAD", "INITCAP", "INSTR",
    "ARRAY_CONTAINS", "ARRAY_SIZE",
    "COLLECT_LIST", "COLLECT_SET",
    "PERCENTILE_APPROX",
    "TO_JSON", "FROM_JSON", "PARSE_JSON", "GET_JSON_OBJECT",
    "EXPLODE", "POSEXPLODE",
}



def _collect_schema_columns(db_connection: DatabaseConnectionModel) -> Set[str]:
    """
    Build a lowercase set of every column name present in the datasource schema.
    We deliberately include columns from all tables because metric formulas may
    span joins and we only check identifier existence here, not table affinity.
    """
    cols: Set[str] = set()
    ds_graph = _safe_json_loads(db_connection.ds_graph_json, {})
    for node in ds_graph.get("nodes", []) or []:
        for col in node.get("columns", []) or []:
            name = (col.get("name") or "").strip()
            if name:
                cols.add(name.lower())
    # Some pipelines also stash column lists under db_schema → tables[].columns[]
    schema = _safe_json_loads(db_connection.db_schema, {})
    for table in schema.get("tables", []) or []:
        for col in table.get("columns", []) or []:
            name = (col.get("name") or "").strip() if isinstance(col, dict) else ""
            if name:
                cols.add(name.lower())
    return cols


def _extract_identifiers_from_formula(formula: str) -> Set[str]:
    """
    Pull out plausible column-name references from a metric formula string.
    Handles both `alias.column` (returns "column") and bare `column` tokens,
    while filtering out SQL keywords, function names, and type names.

    Key filter: identifiers immediately followed by '(' are SQL function calls
    (e.g. TIMESTAMPDIFF, DATEDIFF, AGE, DATE_FORMAT) and are always skipped,
    even if their name does not appear in _SQL_RESERVED_TOKENS. This prevents
    dialect-specific function names from being incorrectly flagged as missing
    schema columns, which was causing infinite clarification loops.
    """
    if not isinstance(formula, str) or not formula.strip():
        return set()

    identifiers: Set[str] = set()
    # Pattern matches either `alias.column` or a bare identifier.
    # Groups: (1)=alias, (2)=qualified-column; (3)=bare identifier (when no dot).
    pattern = re.compile(
        r"([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)|([A-Za-z_][A-Za-z0-9_]*)"
    )
    for match in pattern.finditer(formula):
        _alias, qualified_col, bare = match.group(1), match.group(2), match.group(3)
        if qualified_col:
            # Take the column part only; the alias is a SQL-local alias, not a real column.
            identifiers.add(qualified_col.lower())
            continue
        if bare:
            if bare.upper() in _SQL_RESERVED_TOKENS:
                continue
            # Skip pure numeric tokens (regex excludes leading digits, but be safe).
            if bare.isdigit():
                continue
            # Skip SQL function calls: any identifier followed by optional whitespace
            # then '(' is a function name, not a column reference.  This handles
            # dialect-specific functions like TIMESTAMPDIFF, DATEDIFF, AGE, DATE_FORMAT,
            # NVL, TRUNC, CALENDAR_MONTH, etc. that are not in _SQL_RESERVED_TOKENS.
            rest = formula[match.end():]
            if rest.lstrip().startswith("("):
                continue
            identifiers.add(bare.lower())
    return identifiers


def _validate_metric_formula_columns(
    ontology: Dict[str, Any],
    db_connection: DatabaseConnectionModel,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Walk every metric in the enriched ontology and verify that each identifier
    in its `formula` and `denominator` exists somewhere in the schema.
    Metrics with unresolvable columns are stripped out and reported.

    Returns (cleaned_ontology, warnings) where each warning is:
        {
            "metric_name": "...",
            "formula": "...",
            "missing_columns": ["payment_value", ...],
            "action": "dropped"
        }
    """
    warnings: List[Dict[str, Any]] = []
    metrics = ontology.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        return ontology, warnings

    schema_cols = _collect_schema_columns(db_connection)
    if not schema_cols:
        # No schema info available; skip validation rather than wrongly reject everything.
        return ontology, warnings

    kept: List[Dict[str, Any]] = []
    for metric in metrics:
        if not isinstance(metric, dict):
            kept.append(metric)
            continue

        formula = (metric.get("formula") or "").strip()
        denominator = (metric.get("denominator") or "").strip()
        # Metrics whose id follows the enrichment pattern "metric:<name>" were added
        # by the enrichment flow and MUST have a formula.  Drop them if they slipped
        # through without one — they are unresolved pending stubs and would show up
        # as null-property entries in the ontology viewer.
        metric_id = str(metric.get("id") or "")
        if not formula and not denominator:
            if metric_id.startswith("metric:"):
                warnings.append({
                    "metric_name": metric.get("name") or "(unnamed metric)",
                    "formula": "",
                    "missing_columns": [],
                    "action": "dropped_no_formula",
                })
                logger.warning(
                    "Dropping enrichment metric '%s' (id=%s): no formula was resolved.",
                    metric.get("name"),
                    metric_id,
                )
                continue
            kept.append(metric)
            continue

        identifiers = _extract_identifiers_from_formula(formula) | _extract_identifiers_from_formula(denominator)
        if not identifiers:
            kept.append(metric)
            continue

        missing = sorted(ident for ident in identifiers if ident not in schema_cols)
        if not missing:
            kept.append(metric)
            continue

        warnings.append({
            "metric_name": metric.get("name") or "(unnamed metric)",
            "formula": formula or denominator,
            "missing_columns": missing,
            "action": "dropped",
        })
        logger.warning(
            "Dropping metric '%s' from enriched ontology: formula references "
            "columns that do not exist in schema: %s. Formula: %s",
            metric.get("name"),
            missing,
            formula or denominator,
        )

    cleaned = dict(ontology)
    cleaned["metrics"] = kept
    if warnings:
        cleaned.setdefault("metadata", {})["metric_validation_warnings"] = warnings
    return cleaned, warnings


def _get_connection_or_404(db: Session, connection_id: UUID) -> DatabaseConnectionModel:
    connection = db.query(DatabaseConnectionModel).filter(DatabaseConnectionModel.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database connection not found")
    if not connection.ds_graph_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Datasource graph not available yet. Please complete schema extraction first.",
        )
    return connection


def _get_latest_ontology_version(db: Session, connection_id: UUID) -> Optional[OntologyVersionModel]:
    return (
        db.query(OntologyVersionModel)
        .filter(OntologyVersionModel.datasource_connection_id == connection_id)
        .order_by(OntologyVersionModel.version_number.desc())
        .first()
    )


@require_permission(Permission.VIEW_DATASOURCE)
async def get_latest_ontology(connection_id: UUID, db: Session = Depends(get_db), token_payload: dict = None):
    _get_connection_or_404(db, connection_id)
    version = _get_latest_ontology_version(db, connection_id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ontology not built yet")

    graph_payload = _safe_json_loads(version.graph_json, {"nodes": [], "edges": [], "stats": {}})
    ontology_payload = _safe_json_loads(version.ontology_json, {})

    return {
        "ontology_version_id": str(version.id),
        "version_label": version.version_label,
        "status": version.status,
        "is_base": bool(version.is_base),
        "graph": graph_payload,
        "ontology": ontology_payload,
    }


@require_permission(Permission.VIEW_DATASOURCE)
async def get_latest_ontology_ttl(connection_id: UUID, db: Session = Depends(get_db), token_payload: dict = None):
    _get_connection_or_404(db, connection_id)
    version = _get_latest_ontology_version(db, connection_id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ontology not built yet")

    ttl = version.ontology_ttl
    if not ttl:
        ontology_payload = _safe_json_loads(version.ontology_json, {})
        ttl = _ontology_to_ttl(ontology_payload)
        version.ontology_ttl = ttl
        db.commit()
    return ttl


@require_permission(Permission.VIEW_DATASOURCE)
async def validate_latest_ontology_ttl(connection_id: UUID, db: Session = Depends(get_db), token_payload: dict = None):
    """
    Lightweight Turtle validation for current ontology snapshot.
    """
    ttl = await get_latest_ontology_ttl(connection_id, db, token_payload)
    lines = [ln.strip() for ln in ttl.splitlines() if ln.strip()]
    errors: List[str] = []

    required_prefixes = [
        "@prefix ex:",
        "@prefix owl:",
        "@prefix rdfs:",
    ]
    for p in required_prefixes:
        if not any(ln.startswith(p) for ln in lines):
            errors.append(f"Missing required prefix: {p}")

    triple_lines = [ln for ln in lines if not ln.startswith("@prefix")]
    if not triple_lines:
        errors.append("No triples found in TTL body.")

    malformed = [ln for ln in triple_lines if not ln.endswith(".")]
    if malformed:
        errors.append(f"{len(malformed)} triple line(s) do not end with '.'.")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "triple_count": len(triple_lines),
    }


@require_permission(Permission.EDIT_DATASOURCE)
async def bootstrap_ontology(connection_id: UUID, db: Session = Depends(get_db), token_payload: dict = None):
    db_connection = _get_connection_or_404(db, connection_id)
    latest = _get_latest_ontology_version(db, connection_id)
    if latest:
        return await get_latest_ontology(connection_id, db, token_payload)

    ontology = _build_base_ontology(db_connection)
    ontology = await _llm_refine_ontology(
        ontology=ontology,
        db_schema_json=db_connection.db_schema,
        db_type=db_connection.db_type,
    )
    graph = _ontology_to_graph(ontology)

    user_id = token_payload.get("sub") if token_payload else None

    version = OntologyVersionModel(
        id=uuid4(),
        datasource_connection_id=connection_id,
        version_number=1,
        version_label="base_v1",
        status="published",
        is_base=True,
        ontology_json=json.dumps(ontology),
        ontology_ttl=_ontology_to_ttl(ontology),
        graph_json=json.dumps(graph),
        created_by=UUID(user_id) if user_id else None,
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    return {
        "ontology_version_id": str(version.id),
        "version_label": version.version_label,
        "status": version.status,
        "is_base": bool(version.is_base),
        "graph": graph,
        "ontology": ontology,
    }


@require_permission(Permission.EDIT_DATASOURCE)
async def start_enrichment(connection_id: UUID, db: Session = Depends(get_db), token_payload: dict = None):
    await bootstrap_ontology(connection_id, db, token_payload)
    base_version = _get_latest_ontology_version(db, connection_id)
    if not base_version:
        raise HTTPException(status_code=500, detail="Failed to prepare base ontology")

    ontology = _safe_json_loads(base_version.ontology_json, {})

    user_id = token_payload.get("sub") if token_payload else None

    initial_message = (
        "Ontology enrichment chat started. "
        "Tell me your metric definitions, default date dimension/granularity, status meanings, "
        "and any default filters. You can ask follow-up questions too."
    )
    initial_state = {
        "chat_history": [{"role": "assistant", "content": initial_message}],
        "updates": {},
    }

    session = OntologyEnrichmentSessionModel(
        id=uuid4(),
        datasource_connection_id=connection_id,
        base_ontology_version_id=base_version.id,
        status="in_progress",
        questions_json=json.dumps({"mode": "chat"}),
        answers_json=json.dumps(initial_state),
        created_by=UUID(user_id) if user_id else None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return {
        "session_id": str(session.id),
        "ontology_version_id": str(base_version.id),
        "initial_message": initial_message,
    }


@require_permission(Permission.EDIT_DATASOURCE)
async def enrichment_chat_message(
    connection_id: UUID,
    session_id: UUID,
    message: str,
    db: Session = Depends(get_db),
    token_payload: dict = None,
):
    db_connection = _get_connection_or_404(db, connection_id)
    session = (
        db.query(OntologyEnrichmentSessionModel)
        .filter(
            OntologyEnrichmentSessionModel.id == session_id,
            OntologyEnrichmentSessionModel.datasource_connection_id == connection_id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Enrichment session not found")
    if session.status != "in_progress":
        raise HTTPException(status_code=400, detail="Enrichment session is not active")

    base_version = db.query(OntologyVersionModel).filter(OntologyVersionModel.id == session.base_ontology_version_id).first()
    if not base_version:
        raise HTTPException(status_code=404, detail="Base ontology version not found")

    state = _safe_json_loads(session.answers_json, {"chat_history": [], "updates": {}})
    chat_history = state.get("chat_history", [])
    updates = state.get("updates", {})

    chat_history.append({"role": "user", "content": message})
    ontology = _safe_json_loads(base_version.ontology_json, {})
    llm_resp = await _llm_enrichment_chat(
        ontology, chat_history, message, str(session_id), db_type=db_connection.db_type
    )
    assistant_message = llm_resp.get("assistant_message") or "I'm here to help! Feel free to share your business metrics, reporting rules, or any date preferences you'd like to set up."
    extracted_updates = llm_resp.get("extracted_updates") or {}
    needs_clarification = bool(llm_resp.get("needs_clarification"))

    if isinstance(extracted_updates, dict):
        # Deep merge so successive messages accumulate correctly.
        # Shallow update() would wipe earlier rules/metrics if the same top-level key appears again.
        # e.g. msg1: {"rules": {"default_time_granularity": "week"}}
        #      msg2: {"rules": {"default_time_dimension": "order_date"}}
        # → both should survive in updates["rules"] together.
        for key, value in extracted_updates.items():
            if key in updates and isinstance(updates[key], dict) and isinstance(value, dict):
                if key == "metrics":
                    # Metric-level deep merge so a pending clarification can clear
                    # previously stored formula fields for the same metric.
                    for metric_name, metric_update in value.items():
                        # Case-insensitive lookup: the LLM may capitalise the metric name
                        # differently across turns (e.g. "revenue per customer" in turn-1
                        # and "Revenue Per Customer" in turn-2).  Without this, both spellings
                        # end up as separate keys and the null-formula stub survives to apply.
                        existing_key = next(
                            (k for k in updates[key] if k.lower() == metric_name.lower()),
                            None,
                        )
                        if (
                            existing_key
                            and isinstance(updates[key][existing_key], dict)
                            and isinstance(metric_update, dict)
                        ):
                            updates[key][existing_key].update(metric_update)
                            if (
                                str(metric_update.get("status") or "").lower() == "pending"
                                and not str(metric_update.get("formula") or "").strip()
                            ):
                                updates[key][existing_key].pop("formula", None)
                        else:
                            # Don't persist brand-new pending stubs (no formula yet) into
                            # session updates.  They have no formula so if apply is triggered
                            # before the user finishes the clarification flow they would land
                            # in the ontology as null-property metrics.  The pending context
                            # is already captured in chat_history for the LLM to use.
                            incoming_formula = str(metric_update.get("formula") or "").strip()
                            incoming_status = str(metric_update.get("status") or "").lower()
                            if not incoming_formula and incoming_status == "pending":
                                continue
                            updates[key][metric_name] = metric_update
                else:
                    updates[key].update(value)
            elif key in updates and isinstance(updates[key], list) and isinstance(value, list):
                # For lists (e.g. aliases), append new items without duplicating by term
                existing_terms = {item.get("term") for item in updates[key] if isinstance(item, dict) and "term" in item}
                for item in value:
                    if isinstance(item, dict) and item.get("term") not in existing_terms:
                        updates[key].append(item)
            else:
                updates[key] = value
    chat_history.append({"role": "assistant", "content": assistant_message})

    session.answers_json = json.dumps({"chat_history": chat_history, "updates": updates})
    db.commit()

    return {
        "session_id": str(session.id),
        "assistant_message": assistant_message,
        "extracted_updates": updates,
        "chat_history": chat_history,
        "needs_clarification": needs_clarification,
    }


@require_permission(Permission.EDIT_DATASOURCE)
async def submit_enrichment_answers(
    connection_id: UUID,
    session_id: UUID,
    answers: List[Dict[str, Any]],
    db: Session = Depends(get_db),
    token_payload: dict = None,
):
    submit_start = time.perf_counter()
    db_connection = _get_connection_or_404(db, connection_id)

    session = (
        db.query(OntologyEnrichmentSessionModel)
        .filter(
            OntologyEnrichmentSessionModel.id == session_id,
            OntologyEnrichmentSessionModel.datasource_connection_id == connection_id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Enrichment session not found")

    base_version = db.query(OntologyVersionModel).filter(OntologyVersionModel.id == session.base_ontology_version_id).first()
    if not base_version:
        raise HTTPException(status_code=404, detail="Base ontology version not found")

    state = _safe_json_loads(session.answers_json, {})
    answers_map = {}
    if isinstance(state, dict):
        answers_map = state.get("updates", {}) or {}
    if not answers_map:
        answers_map = {}
    # Merge any additional frontend-provided answers, but only if they are richer
    # than what the session already has. This prevents the frontend from overwriting
    # correctly-typed nested dicts with "[object Object]" strings.
    for item in answers:
        qid = item.get("question_id")
        answer = item.get("answer")
        if not qid or answer is None:
            continue
        existing = answers_map.get(qid)
        # Skip if the incoming value is a plain string and the session already holds a dict
        if isinstance(existing, dict) and isinstance(answer, str):
            continue
        if isinstance(existing, list) and isinstance(answer, str):
            continue
        answers_map[qid] = answer

    # Strip any pending (formula-less) metric stubs that were never resolved before
    # the user pressed Apply.  These arise when a clarification flow was abandoned
    # mid-way: the stub has a description but no formula and would be persisted as a
    # null-property metric in the new ontology version.
    if isinstance(answers_map.get("metrics"), dict):
        answers_map["metrics"] = {
            name: data
            for name, data in answers_map["metrics"].items()
            if isinstance(data, dict) and str(data.get("formula") or "").strip()
        }

    base_ontology = _safe_json_loads(base_version.ontology_json, {})
    apply_start = time.perf_counter()
    try:
        enriched_ontology = await _apply_answers_to_ontology(base_ontology, answers_map)
    except Exception as exc:
        logger.warning("apply_answers_to_ontology failed, using base ontology: %s", str(exc))
        enriched_ontology = dict(base_ontology)
        enriched_ontology.setdefault("metadata", {})["enrichment_apply_error"] = True
    apply_elapsed = round(time.perf_counter() - apply_start, 3)

    # Validate metric formulas against the actual schema. Metrics referencing
    # columns that don't exist would be ignored by NL2SQL anyway (it has strict
    # "no column hallucination" rules), so we drop them here and tell the user.
    try:
        enriched_ontology, metric_warnings = _validate_metric_formula_columns(
            enriched_ontology, db_connection
        )
    except Exception as exc:
        logger.warning("Metric formula validation failed (non-fatal): %s", str(exc))
        metric_warnings = []

    # Skip post-enrichment LLM refinement: the ontology was already refined at bootstrap
    # and re-running refinement on large ontologies (80–100 KB) causes timeouts that
    # would strip the user-provided business definitions before they can be saved.
    try:
        enriched_graph = _ontology_to_graph(enriched_ontology)
    except Exception as exc:
        logger.warning("_ontology_to_graph failed, building empty graph: %s", str(exc))
        enriched_graph = {"nodes": [], "edges": [], "stats": {"class_count": 0, "metric_count": 0, "relation_count": 0}}
    graph_elapsed = round(time.perf_counter() - apply_start, 3) - apply_elapsed

    latest = _get_latest_ontology_version(db, connection_id)
    next_version = 1 if not latest else latest.version_number + 1

    user_id = token_payload.get("sub") if token_payload else None

    new_version = OntologyVersionModel(
        id=uuid4(),
        datasource_connection_id=connection_id,
        version_number=next_version,
        version_label=f"enriched_v{next_version}",
        status="published",
        is_base=False,
        ontology_json=json.dumps(enriched_ontology),
        ontology_ttl=_ontology_to_ttl(enriched_ontology),
        graph_json=json.dumps(enriched_graph),
        created_by=UUID(user_id) if user_id else None,
    )

    session.answers_json = json.dumps({"chat_history": state.get("chat_history", []), "updates": answers_map})
    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)

    db.add(new_version)
    db.commit()
    db.refresh(new_version)
    total_elapsed = round(time.perf_counter() - submit_start, 3)
    logger.info(
        "Ontology apply completed | connection_id=%s | session_id=%s | apply_s=%s | graph_s=%s | total_s=%s | updates_keys=%s",
        str(connection_id),
        str(session_id),
        apply_elapsed,
        round(max(graph_elapsed, 0.0), 3),
        total_elapsed,
        list(answers_map.keys()),
    )

    return {
        "ontology_version_id": str(new_version.id),
        "version_label": new_version.version_label,
        "status": new_version.status,
        "is_base": False,
        "graph": enriched_graph,
        "ontology": enriched_ontology,
        "metric_warnings": metric_warnings,
    }


_DAX_TRANSLATION_SYSTEM_PROMPT = """\
You are a DAX-to-SQL translation expert for a NL2SQL system.
You will receive a list of Power BI DAX measures and must convert each one into a
SQL formula compatible with the specified database dialect, using ONLY the available
tables and columns from the user's connected datasource.

Rules:
- Translate the business intent of the DAX expression into SQL using the available schema.
- Use ONLY real table.column names from the provided schema_columns.
- Follow the SQL dialect rules provided below exactly.
- Preserve the business meaning of each measure.
- Do NOT hallucinate table or column names.
- If a measure cannot be reliably translated (e.g. it references Power BI-only
  functions, calculated tables, or columns not in the schema), mark it as
  status="pending" with an empty formula and include a brief translation_error.

══════════════════════════════════════════════════
METRIC FORMULA FORMAT — CRITICAL RULE
══════════════════════════════════════════════════
- Metrics are EXPRESSIONS, not SQL queries.
- Output MUST contain only the metric formula (aggregation expression).
- Table references must use table.column format.
- Generated formulas must be compatible with the existing ontology metric validation pipeline.

FORBIDDEN CONSTRUCTS:
You MUST NOT generate any of the following:
  ✗ SELECT
  ✗ FROM
  ✗ JOIN
  ✗ GROUP BY
  ✗ ORDER BY
  ✗ HAVING
  ✗ WITH
  ✗ CTEs
  ✗ Nested SELECT statements
  ✗ Standalone SQL queries

POSITIVE EXAMPLES (DO THIS):
  ✓ SUM(order_header.price)
  ✓ COUNT(order_header.order_id)
  ✓ COUNT(DISTINCT order_header.customer_id)
  ✓ SUM(order_header.price) - SUM(sale_return.refund_amount)
  ✓ AVG(order_header.price)
  ✓ CASE WHEN order_header.status = 'COMPLETED' THEN order_header.price ELSE 0 END

NEGATIVE EXAMPLES (NEVER DO THIS):
  ✗ SELECT SUM(price) FROM order_header
  ✗ (SELECT SUM(refund_amount) FROM sale_return)
  ✗ SELECT COUNT(*) FROM order_header
  ✗ WITH sales AS (...) SELECT ...

Output format — return a JSON array:
[
  {
    "name": "Measure Name",
    "description": "Plain English description",
    "formula": "SQL expression or empty string",
    "status": "active" or "pending",
    "translation_error": "reason if pending, else empty string"
  }
]
"""


def _extract_measures_from_pbit(file_bytes: bytes) -> List[Dict[str, Any]]:
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            schema_names = [n for n in zf.namelist() if "DataModelSchema" in n]
            if not schema_names:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Unable to extract DataModelSchema from the uploaded .pbit file.",
                )
            with zf.open(schema_names[0]) as schema_file:
                raw = schema_file.read()
            try:
                schema_text = raw.decode("utf-16-le")
            except UnicodeDecodeError:
                schema_text = raw.decode("utf-8", errors="replace")
            schema = json.loads(schema_text)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to extract DataModelSchema from the uploaded .pbit file.",
        ) from exc

    measures: List[Dict[str, Any]] = []
    for table in schema.get("model", {}).get("tables", []):
        table_name = table.get("name", "")
        for measure in table.get("measures", []):
            name = measure.get("name", "").strip()
            raw_expr = measure.get("expression") or ""
            if isinstance(raw_expr, list):
                raw_expr = "\n".join(str(part) for part in raw_expr)
            expression = str(raw_expr).strip()
            if name:
                measures.append({"table": table_name, "name": name, "expression": expression})
    return measures


async def _translate_dax_measures(
    measures: List[Dict[str, Any]],
    schema_columns: Dict[str, list],
    db_type: Optional[str],
) -> List[Dict[str, Any]]:
    dialect_instructions = _get_db_type_sql_instructions(db_type)
    system_prompt = _DAX_TRANSLATION_SYSTEM_PROMPT + "\n" + dialect_instructions

    user_payload = json.dumps(
        {
            "db_type": db_type or "unknown",
            "schema_columns": schema_columns,
            "measures": measures,
        },
        ensure_ascii=False,
    )

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        result = await llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_payload),
            ]
        )
        raw_content = result.content if hasattr(result, "content") else str(result)
        json_match = re.search(r"\[.*\]", raw_content, re.DOTALL)
        if not json_match:
            raise ValueError("LLM did not return a JSON array")
        translated: List[Dict[str, Any]] = json.loads(json_match.group(0))
        if not isinstance(translated, list):
            raise ValueError("Unexpected LLM response shape")
        return translated
    except Exception as exc:
        logger.warning("DAX translation LLM call failed: %s", str(exc))
        return [
            {
                "name": m["name"],
                "description": f"Imported from Power BI (table: {m['table']})",
                "formula": "",
                "status": "pending",
                "translation_error": f"Translation failed: {str(exc)}",
            }
            for m in measures
        ]


@require_permission(Permission.EDIT_DATASOURCE)
async def process_pbit_upload(
    connection_id: UUID,
    file: UploadFile,
    db: Session = Depends(get_db),
    token_payload: dict = None,
) -> Dict[str, Any]:
    if not (file.filename or "").lower().endswith(".pbit"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .pbit files are supported.",
        )

    db_connection = _get_connection_or_404(db, connection_id)

    file_bytes = await file.read()
    measures = _extract_measures_from_pbit(file_bytes)
    del file_bytes

    if not measures:
        return {"status": "success", "imported_metrics": 0, "pending_metrics": 0, "duplicate_metrics": 0}

    latest_version = _get_latest_ontology_version(db, connection_id)
    if not latest_version:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No ontology found for this connection. Please bootstrap the ontology first.",
        )

    current_ontology = _safe_json_loads(latest_version.ontology_json, {})
    schema_columns = _build_enrichment_schema_columns(current_ontology)
    ont_classes: List[Dict[str, Any]] = [
        c for c in (current_ontology.get("classes") or []) if isinstance(c, dict)
    ]

    translated = await _translate_dax_measures(measures, schema_columns, db_connection.db_type)

    existing_metrics: List[Dict[str, Any]] = [
        m for m in (current_ontology.get("metrics") or []) if isinstance(m, dict)
    ]
    existing_names_lower = {str(m.get("name") or "").lower() for m in existing_metrics}

    imported_count = 0
    pending_count = 0
    duplicate_count = 0

    for item in translated:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        name_lower = name.lower()
        if name_lower in existing_names_lower:
            logger.info("Skipping duplicate PBIT metric: %s", name)
            duplicate_count += 1
            continue

        formula = str(item.get("formula") or "").strip()
        metric_status = str(item.get("status") or "active").strip()
        description = str(item.get("description") or f"Imported from Power BI").strip()

        if not formula:
            metric_status = "pending"

        new_metric: Dict[str, Any] = {
            "id": f"metric:{name}",
            "name": name,
            "definition": description,
            "formula": formula,
        }

        if item.get("translation_error"):
            new_metric["translation_error"] = str(item["translation_error"])

        if formula:
            inferred_class = _infer_class_from_formula(formula, ont_classes)
            if inferred_class:
                new_metric["based_on_class"] = inferred_class

        existing_metrics.append(new_metric)
        existing_names_lower.add(name_lower)

        if metric_status == "pending":
            pending_count += 1
        else:
            imported_count += 1

    updated_ontology = dict(current_ontology)
    updated_ontology["metrics"] = existing_metrics

    try:
        updated_ontology, _ = _validate_metric_formula_columns(updated_ontology, db_connection)
    except Exception as exc:
        logger.warning("Metric formula validation failed during PBIT import (non-fatal): %s", str(exc))

    try:
        updated_graph = _ontology_to_graph(updated_ontology)
    except Exception as exc:
        logger.warning("_ontology_to_graph failed during PBIT import: %s", str(exc))
        updated_graph = _safe_json_loads(latest_version.graph_json, {"nodes": [], "edges": [], "stats": {}})

    next_version_number = latest_version.version_number + 1
    user_id = token_payload.get("sub") if token_payload else None

    new_version = OntologyVersionModel(
        id=uuid4(),
        datasource_connection_id=connection_id,
        version_number=next_version_number,
        version_label=f"pbit_import_v{next_version_number}",
        status="published",
        is_base=False,
        ontology_json=json.dumps(updated_ontology),
        ontology_ttl=_ontology_to_ttl(updated_ontology),
        graph_json=json.dumps(updated_graph),
        created_by=UUID(user_id) if user_id else None,
    )
    db.add(new_version)
    db.commit()
    db.refresh(new_version)

    logger.info(
        "PBIT import complete | connection_id=%s | imported=%d | pending=%d | duplicates=%d",
        str(connection_id), imported_count, pending_count, duplicate_count,
    )

    return {
        "status": "success",
        "imported_metrics": imported_count,
        "pending_metrics": pending_count,
        "duplicate_metrics": duplicate_count,
    }
