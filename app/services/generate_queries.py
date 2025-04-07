from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from uuid import UUID
from typing import Any
import httpx
from app.models.schema_models import ChartModel, DashboardChartsModel, DatabaseConnectionModel
from app.schemas import QueryRequest

# Correct LLM endpoint
LLM_SERVICE_URL = "http://127.0.0.1:8000/queries/"

# Properly await everything in this helper
async def post_to_llm(url: str, payload: dict) -> Any:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)  # ✅ await the post
            response.raise_for_status()
            return response.json() 
    except httpx.RequestError as e:
        raise Exception(f"Error communicating with LLM service at {url}: {str(e)}")
    except httpx.HTTPStatusError as e:
        raise Exception(f"LLM service error: {str(e.response.status_code)} - {str(e.response.text)}")


# Main chart generation logic
async def generate_and_store_charts(
    db: Session,
    dashboard_id: UUID,
    project_id: UUID,
    query_request: QueryRequest,
):
    db_conn = db.query(DatabaseConnectionModel).filter_by(project_id=project_id).first()
    if not db_conn:
        raise HTTPException(status_code=404, detail="No database connection found for this project")

    llm_payload = {
        "db_schema": db_conn.db_schema,
        "db_type": query_request.db_type,
        "role": query_request.role,
        "domain": query_request.domain,
        "min_date": query_request.min_date,
        "max_date": query_request.max_date,
        "api_key": query_request.api_key,
    }

    llm_response = await post_to_llm(LLM_SERVICE_URL, llm_payload)
    queries = llm_response.get("queries", [])

    chart_models = []
    for q in queries:
        chart = ChartModel(
            title=q["explanation"][:80],
            query=q["query"],
            report=q["explanation"],
            type=q["chart_type"],
            relevance=q["relevance"],
            is_time_based=q["is_time_based"],
            chart_type=q["chart_type"],
            is_user_generated=False,
        )
        db.add(chart)
        db.flush()

        # assoc = DashboardChartsModel(
        #     chart_id=chart.id,
        #     dashboard_id=dashboard_id,
        # )
        # db.add(assoc)
        chart_models.append(chart)

    db.commit()
    return chart_models
