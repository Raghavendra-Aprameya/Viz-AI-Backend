import os
import logging
import traceback
from typing import List
from uuid import UUID
import httpx
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.utils.token_parser import  get_current_user
from app.models.schema_models import DatabaseConnectionModel, ChartModel
from app.schemas import TrinoQueryRequest, TrinoQueryResponse, QueryDetail
from app.utils.schema_structure import get_schema_structure
from app.utils.crypt import decrypt_string


logger = logging.getLogger(__name__)
LLM_ENDPOINT = "http://localhost:8001/generate_multiple_db_queries"

def parse_query_metadata(response: dict):
    parsed_queries = []
    for item in response.get("queries", []):
        parsed = {
            "sql": item.get("query", "").strip(),
            "title": item.get("explanation", "").strip(),
            "chart_type": item.get("chart_type", "").strip(),
            "relevance": float(item.get("relevance", 0.0)),
            "is_time_based": bool(item.get("is_time_based", False))
        }
        parsed_queries.append(parsed)
    return parsed_queries

async def generate_trino_queries_service(
    db: Session,
    project_id: UUID,
    request: TrinoQueryRequest,
    token_payload: dict = Depends(get_current_user),
    
) -> TrinoQueryResponse:
    try:
        user_id_str = token_payload.get("sub")
        if not user_id_str:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

        try:
            user_id = UUID(user_id_str)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid UUID format in token")
        # Fetch database connections
        connections = db.query(DatabaseConnectionModel).filter(
            DatabaseConnectionModel.id.in_(request.connection_ids)
        ).all()
        if not connections:
            raise ValueError("No valid database connections found")

        # Prepare schema and payload data
        schema_infos = []
        payloads = []

        for conn in connections:
            payload = {
                "connection_schema": conn.db_schema
                # "db_type": conn.db_type,
                # "catalog": conn.catalog or "default",
                # "schema_name": conn.schema or "public"
            }
            # schema_info = await get_schema_structure(payload)
            payloads.append(payload)
            schema_infos.append(payload)

        schemas = schema_infos
        catalogs = ["neondb","classicmodels"]
        schema_names = ["public","classicmodels"]
        min_dates = [s.get("min_date") for s in schema_infos if s.get("min_date")]
        max_dates = [s.get("max_date") for s in schema_infos if s.get("max_date")]
        min_date = str(min(min_dates)) if min_dates else None
        max_date = str(max(max_dates)) if max_dates else None

        # Prepare LLM request
        api_key = request.api_key or os.getenv("GEMINI_API_KEY")
        payload = {
            "schema_payloads": schemas,
            "catalogs": catalogs,
            "schema_names": schema_names,
            "role": request.role,
            "domain": request.domain,
            "min_date": min_date,
            "max_date": max_date,
            "api_key": api_key,
            "model_name": request.model_name or "gemini-1.5-pro"
        }

        # Call LLM service
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(LLM_ENDPOINT, json=payload, )
            resp.raise_for_status()
            raw_response = resp.json()

        # Parse LLM response
        parsed_queries = parse_query_metadata(raw_response)
        queries = [QueryDetail(**q) for q in parsed_queries]

        # Optionally store charts
        for detail in queries:
            chart = ChartModel(
                # project_id=project_id,
                title=detail.title,
                query=detail.sql,
                type=detail.chart_type,
                chart_type=detail.chart_type,
                relevance=detail.relevance,
                is_time_based=detail.is_time_based,
                report=detail.result,
                created_by=user_id,
                is_user_generated=False
            )
            db.add(chart)
        db.commit()

        return TrinoQueryResponse(
            queries=queries,
            min_date=min_date,
            max_date=max_date
        )

    except Exception as e:
        logger.error(f"Failed to generate Trino queries: {e}\n{traceback.format_exc()}")
        raise
