from fastapi import HTTPException, status, Request, Depends
import jwt
from app.core.settings import settings

async def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")
    
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

# Keep the original parse_token for backward compatibility
def parse_token(request: Request):
    return get_current_user(request)# from time import sleep
# from turtle import back
# from celery import Celery
# from app.services.generate_queries import generate_and_store_charts
# import logging


# logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.INFO)


# celery_app = Celery('tasks', broker='redis://localhost:6379/0',backend='redis://localhost:6379/0')

# # @app.task
# # def generate_charts_asynchronously():
# #     #write code to generate charts
# #     chart_models =  generate_and_store_charts(
# #         db=db,
# #         datasource_connection_id=datasource_connection_id,
# #         project_id=project_id,
# #         query_request=query_request,
# #         token_payload=token_payload
# #     )

# #     # Serialize chart data for Redis storage
# #     charts_serialized = [{
# #         "id": str(chart.id),
# #         "title": chart.title,
# #         "chart_type": chart.chart_type,
# #         "created_at": chart.created_at.isoformat() if hasattr(chart, 'created_at') else None
# #     } for chart in chart_models]

# #     # Store current charts in Redis
# #     r.set(f"charts:current:{user_id}", json.dumps(charts_serialized))

# #     # Start background task to generate next batch of charts
# #     generate_charts_asynchronously.delay(user_id, str(datasource_connection_id), str(project_id))

# #     return chart_models
# @celery_app.task
# def generate_charts_asynchronously(
#     user_id,
#     datasource_connection_id=None,
#     project_id=None,
#     query_request=None
# ):
#     """
#     Celery task to generate charts asynchronously and store them in Redis
#     for quick access on the next user request.
#     """
#     try:
#         # Create a new database session for this background task
#         db =

#         # Convert string IDs back to UUID objects if provided
#         ds_conn_id = UUID(datasource_connection_id) if datasource_connection_id else None
#         proj_id = UUID(project_id) if project_id else None

#         # Get user token payload from somewhere (depends on your auth system)
#         # This is a placeholder - you'll need to implement a way to get valid token payload
#         token_payload = {"user_id": user_id}

#         # Generate the charts
#         chart_models = generate_and_store_charts(
#             db=db,
#             datasource_connection_id=ds_conn_id,
#             project_id=proj_id,
#             query_request=query_request,
#             token_payload=token_payload
#         )

#         # Serialize chart data for Redis storage
#         charts_serialized = [{
#             "id": str(chart.id),
#             "title": chart.title,
#             "chart_type": chart.chart_type,
#             "created_at": chart.created_at.isoformat() if hasattr(chart, 'created_at') else None,
#             "data": chart.data if hasattr(chart, 'data') else None,
#             # Add other relevant chart fields here
#         } for chart in chart_models]

#         # Store next batch of charts in Redis with expiration (e.g., 1 hour)
#         redis_key = f"charts:next:{user_id}"
#         r.set(redis_key, json.dumps(charts_serialized), ex=3600)

#         logger.info(f"Successfully generated next batch of charts for user {user_id}")

#         # Clean up
#         db.close()

#         return {
#             "status": "success",
#             "message": f"Generated {len(charts_serialized)} charts for next batch",
#             "user_id": user_id
#         }

#     except Exception as e:
#         logger.error(f"Error in generate_charts_asynchronously task: {str(e)}")
#         # If db session was created, ensure it's closed even on error
#         if 'db' in locals():
#             db.close()

#         return {
#             "status": "error",
#             "message": f"Failed to generate next batch of charts: {str(e)}",
#             "user_id": user_id
#         }import json
import json
import logging
from uuid import UUID

from celery import Celery
import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services.generate_queries import generate_and_store_charts
from app.core.settings import settings
from app.schemas import QueryRequest  # Import the QueryRequest schema

logger = logging.getLogger(__name__)


def _build_ontology_constraints(ontology_payload: dict) -> dict:
    classes = ontology_payload.get("classes", []) if isinstance(ontology_payload, dict) else []
    relationships = ontology_payload.get("relationships", []) if isinstance(ontology_payload, dict) else []
    metrics = ontology_payload.get("metrics", []) if isinstance(ontology_payload, dict) else []
    rules = ontology_payload.get("rules", {}) if isinstance(ontology_payload, dict) else {}

    allowed_joins = []
    for rel in relationships:
        src = rel.get("source")
        tgt = rel.get("target")
        if src and tgt:
            allowed_joins.append(
                {
                    "source": src,
                    "target": tgt,
                    "source_column": rel.get("source_column"),
                    "target_column": rel.get("target_column"),
                    "label": rel.get("label"),
                }
            )

    metric_defs = []
    for metric in metrics:
        metric_defs.append(
            {
                "name": metric.get("name"),
                "definition": metric.get("definition"),
                "formula": metric.get("formula"),
                "denominator": metric.get("denominator"),
                "default_filter": metric.get("default_filter"),
            }
        )

    return {
        "class_count": len(classes),
        "allowed_joins": allowed_joins,
        "metrics": metric_defs,
        "default_time_dimension": rules.get("default_time_dimension"),
        "default_time_granularity": rules.get("default_time_granularity"),
        "success_status_values": rules.get("status_success_values", []),
        "default_filters": rules.get("default_filters", {}),
    }

# Celery app config with properly configured serializer
celery_app = Celery(
    "tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0"
)

# Configure Celery to use 'solo' instead of 'fork' on macOS
celery_app.conf.update(
    worker_pool="solo",  # Use solo pool instead of prefork on macOS
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
)

# Redis client
r = redis.Redis(host="localhost", port=6379, db=0)

# Create engine outside of task to avoid recreation
engine = create_engine(
    url=settings.DB_URI,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=5,
    max_overflow=10,
)
TaskSessionLocal = sessionmaker(bind=engine, autoflush=False)


# Function to run async code in synchronous context
def run_async(async_func, *args, **kwargs):
    import asyncio

    # Create a new event loop for this function call
    loop = asyncio.new_event_loop()
    try:
        # Run the async function and return the result
        return loop.run_until_complete(async_func(*args, **kwargs))
    finally:
        # Always close the loop to free up resources
        loop.close()


@celery_app.task
def generate_charts_asynchronously(
    user_id, datasource_connection_id=None, project_id=None, query_request=None
):
    """
    Celery task to generate charts asynchronously and store them in Redis
    for quick access on the next user request.
    """
    try:
        # Create a database session
        db = TaskSessionLocal()

        # Convert string IDs to UUID if provided
        ds_conn_id = (
            UUID(datasource_connection_id) if datasource_connection_id else None
        )
        proj_id = UUID(project_id) if project_id else None

        # Token payload with user ID
        token_payload = {"sub": user_id}

        logger.info(f"Starting chart generation for user {user_id}")

        # Convert the dictionary back to a QueryRequest object
        # This is needed because we pass query_request.dict() when calling the task
        if query_request is not None:
            logger.info(f"Converting dict to QueryRequest: {query_request}")
            query_request_obj = QueryRequest(**query_request)
        else:
            logger.warning(f"No query_request provided for user {user_id}")
            query_request_obj = None

        # Use our helper function to run the async function
        chart_models = run_async(
            generate_and_store_charts,
            db=db,
            datasource_connection_id=ds_conn_id,
            project_id=proj_id,
            query_request=query_request_obj,
            token_payload=token_payload,
        )

        # Serialize for Redis
        charts_serialized = [
            {
                "id": str(chart.id),
                "title": chart.title,
                "chart_type": chart.chart_type,
                "created_at": (
                    chart.created_at.isoformat()
                    if hasattr(chart, "created_at")
                    else None
                ),
                "data": getattr(chart, "data", None),
            }
            for chart in chart_models
        ]

        # Store in Redis
        redis_key = f"charts:next:{user_id}"
        r.set(redis_key, json.dumps(charts_serialized), ex=3600)

        logger.info(f"✅ Successfully generated charts for user {user_id}")
        db.close()

        return {
            "status": "success",
            "message": f"Generated {len(charts_serialized)} charts for next batch",
            "user_id": user_id,
        }

    except Exception as e:
        logger.error(f"❌ Error in generate_charts_asynchronously task: {str(e)}")
        if "db" in locals():
            db.close()
        return {
            "status": "error",
            "message": f"Failed to generate next batch of charts: {str(e)}",
            "user_id": user_id,
        }
import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.schema_models import (
    UserProjectRoleModel,
    DatabaseConnectionModel,
    ChartModel,
    OntologyVersionModel,
)
from app.schemas import Nl2SQLChatRequest
from uuid import UUID
import logging
import os
import re

logger = logging.getLogger(__name__)

def _tokenize_text(value: str) -> list[str]:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value or ""))
    s = re.sub(r"[^A-Za-z0-9]+", " ", s).lower()
    return [t for t in s.split() if t]


def _table_name_from_payload(table_payload: dict) -> str:
    return table_payload.get("table") or table_payload.get("name") or ""


def _focus_schema_by_intent(
    nl_query: str,
    schema_str: str,
    ontology_constraints: dict | None,
    ontology_payload: dict | None,
) -> tuple[str, dict]:
    """
    Recall-first schema focusing.
    Keeps core/neighbor tables and all PK/FK-bearing kept tables.
    Falls back to full schema if parsing fails.
    """
    try:
        schema = json.loads(schema_str or "{}")
        tables = schema.get("tables") or []
        if not isinstance(tables, list) or not tables:
            return schema_str, {"mode": "full", "reason": "no_tables"}

        max_tables = int(os.getenv("ONTOLOGY_SCHEMA_MAX_TABLES", "25"))
        if len(tables) <= max_tables:
            return schema_str, {"mode": "full", "reason": "already_small", "table_count": len(tables)}

        nl_tokens = set(_tokenize_text(nl_query))

        alias_tokens = set()
        metric_tokens = set()
        class_table_map: dict[str, str] = {}
        if isinstance(ontology_payload, dict):
            for a in ontology_payload.get("aliases", []) or []:
                alias = a.get("alias")
                if alias:
                    alias_tokens.update(_tokenize_text(alias))
            for m in ontology_payload.get("metrics", []) or []:
                metric_tokens.update(_tokenize_text(m.get("name", "")))
                metric_tokens.update(_tokenize_text(m.get("definition", "")))
            for c in ontology_payload.get("classes", []) or []:
                cid = c.get("id")
                tname = c.get("table") or c.get("name")
                if cid and tname:
                    class_table_map[cid] = tname

        join_pairs: set[tuple[str, str]] = set()
        for rel in (ontology_constraints or {}).get("allowed_joins", []) or []:
            src = rel.get("source")
            tgt = rel.get("target")
            if src and tgt:
                src_name = class_table_map.get(src, src).split(".")[-1].lower()
                tgt_name = class_table_map.get(tgt, tgt).split(".")[-1].lower()
                join_pairs.add((src_name, tgt_name))
                join_pairs.add((tgt_name, src_name))

        scored: list[tuple[float, dict]] = []
        for t in tables:
            tname = _table_name_from_payload(t)
            tname_l = tname.lower()
            tokens = set(_tokenize_text(tname_l))
            for col in t.get("columns", []) or []:
                tokens.update(_tokenize_text(col.get("name", "")))

            score = 0.0
            score += 4.0 * len(tokens & nl_tokens)
            score += 3.0 * len(tokens & alias_tokens)
            score += 2.0 * len(tokens & metric_tokens)
            # Keep structurally important tables biased up.
            if t.get("primary_keys"):
                score += 0.5
            if t.get("foreign_keys"):
                score += 0.5

            scored.append((score, t))

        scored.sort(key=lambda x: x[0], reverse=True)
        # Keep enough core tables first.
        core_count = max(6, min(max_tables - 4, 12))
        kept = scored[:core_count]
        kept_tables = {_table_name_from_payload(t).lower() for _, t in kept}

        # Expand by one-hop ontology joins to protect join paths.
        expanded = True
        while expanded and len(kept_tables) < max_tables:
            expanded = False
            for a, b in list(join_pairs):
                if a in kept_tables and b not in kept_tables:
                    kept_tables.add(b)
                    expanded = True
                elif b in kept_tables and a not in kept_tables:
                    kept_tables.add(a)
                    expanded = True
                if len(kept_tables) >= max_tables:
                    break

        filtered_tables = []
        for t in tables:
            tname = _table_name_from_payload(t).lower()
            if tname in kept_tables:
                filtered_tables.append(t)

        if not filtered_tables:
            return schema_str, {"mode": "full", "reason": "empty_after_filter"}

        focused_schema = dict(schema)
        focused_schema["tables"] = filtered_tables
        return (
            json.dumps(focused_schema),
            {
                "mode": "focused",
                "original_table_count": len(tables),
                "focused_table_count": len(filtered_tables),
                "kept_tables": [(_table_name_from_payload(t)) for t in filtered_tables],
            },
        )
    except Exception as exc:
        logger.warning("Schema focusing failed; falling back to full schema: %s", str(exc))
        return schema_str, {"mode": "full", "reason": "focus_error"}


async def generate_nl_sql(
    data: Nl2SQLChatRequest,
    db: Session,
    user_id: UUID,
    datasource_connection_id: UUID,
    llm_endpoint: str = "http://127.0.0.1:8001/api/nlq/convert_nl_to_sql",
):
    try:
        # user_roles = db.query(UserProjectRoleModel).filter_by(user_id=user_id).all()
        # if not user_roles:
        #     raise HTTPException(status_code=403, detail="User has no project roles assigned.")

        db_conn = (
            db.query(DatabaseConnectionModel)
            .filter_by(id=datasource_connection_id)
            .first()
        )
        if not db_conn:
            raise HTTPException(
                status_code=404,
                detail="No database connection found for user's projects.",
            )

        schema_str = db_conn.db_schema or "{}"
        db_type = db_conn.db_type
        logger.debug(f"Processing database connection: {db_conn.connection_name}, type: {db_type}")
        payload = {
            "nl_query": data.nl_query,
            "db_schema": schema_str,
            "db_type": db_type or "mysql",
            "api_key": getattr(data, "api_key", None),
        }

        # Enriched ontology context (if available) for hybrid NL->SQL grounding.
        ontology_version = (
            db.query(OntologyVersionModel)
            .filter(OntologyVersionModel.datasource_connection_id == datasource_connection_id)
            .order_by(OntologyVersionModel.version_number.desc())
            .first()
        )
        if ontology_version and ontology_version.ontology_json:
            payload["ontology_context"] = ontology_version.ontology_json
            try:
                ontology_payload = json.loads(ontology_version.ontology_json)
                payload["ontology_constraints"] = _build_ontology_constraints(ontology_payload)
                # User preference: always pass full schema (no trimming).
                payload["db_schema"] = schema_str
                payload["schema_focus"] = {
                    "mode": "full",
                    "reason": "user_disabled_schema_trimming",
                }
            except Exception:
                logger.warning("Failed to parse ontology JSON for structured constraints.")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(llm_endpoint, json=payload)
            response.raise_for_status()
            llm_result = response.json()

        sql_query = llm_result.get("sql_query")
        if not sql_query:
            raise HTTPException(status_code=400, detail="LLM did not return SQL query.")

        # new_chart = ChartModel(
        #     title="Generated Chart",
        #     query=sql_query,
        #     report=llm_result.get("explanation", "Auto-generated"),
        #     type="sql",
        #     relevance=llm_result.get("relevance", 1.0),
        #     is_time_based=llm_result.get("is_time_based", False),
        #     chart_type=llm_result.get("chart_type", "unknown"),
        #     is_user_generated=True
        # )

        # db.add(new_chart)
        # db.commit()

        ontology_explanation = {
            "ontology_enabled": bool(ontology_version and ontology_version.ontology_json),
            "ontology_version_id": str(ontology_version.id) if ontology_version else None,
            "ontology_version_label": ontology_version.version_label if ontology_version else None,
            "constraints_summary": payload.get("ontology_constraints", {}),
            "llm_explanation": llm_result.get("explanation"),
        }

        return {
            "status": "success",
            "sql": sql_query,
            "sql_query": sql_query,
            "explanation": llm_result.get("explanation", "Generated SQL using schema and ontology context."),
            "ontology_explanation": ontology_explanation,
            "schema_focus": payload.get("schema_focus", {"mode": "full"}),
            # "chart_id": str(new_chart.id)
        }

    except httpx.HTTPStatusError as e:
        logger.error("LLM service error: %s", e.response.text)
        raise HTTPException(
            status_code=e.response.status_code, detail=f"LLM error: {e.response.text}"
        )
    except httpx.RequestError as e:
        logger.error("LLM request failed: %s", str(e))
        raise HTTPException(status_code=500, detail=f"LLM request failed: {str(e)}")
    except Exception as e:
        logger.exception("Failed to generate/save SQL query")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
