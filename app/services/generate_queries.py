from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from uuid import UUID
import requests
import httpx
from typing import any
from app.models import DatabaseConnectionModel, ChartModel
from app.schemas import QueryRequest, QueriesForExecutorResponse, QueryForExecutor

LLM_SERVICE_URL = "http://localhost:8001/api/llm/generate-queries"  # Update with actual LLM service URL

def get_db_connection(db_id: UUID, db: Session) -> DatabaseConnectionModel:
    db_connection = db.query(DatabaseConnectionModel).filter(DatabaseConnectionModel.id == db_id).first()
    if not db_connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Database connection with ID {db_id} not found."
        )
    return db_connection

async def generate_charts_for_db(
    db: AsyncSession,
    db_id: UUID,
    query_request: QueryRequest,
    llm_url: str
):
    db_conn = await get_db_connection(db, db_id)

    # Call LLM service
    response_json = await post_to_ms(llm_url, query_request.dict())

    queries = response_json.get("queries", [])
    chart_models = []

    for query_data in queries:
        chart = ChartModel(
            title=query_data["explanation"][:80],  # Or custom logic
            query=query_data["query"],
            report=query_data["explanation"],
            type=query_data["chart_type"],
            relevance=query_data["relevance"],
            is_time_based=query_data["is_time_based"],
            chart_type=query_data["chart_type"],
            is_user_generated=False,
        )
        db.add(chart)
        chart_models.append(chart)

    await db.commit()
    return chart_models

def save_llm_charts(response: QueriesForExecutorResponse, db_id: UUID, db: Session):
    charts = []
    for item in response.queries:
        chart = ChartModel(
            title=item.chart_type.replace("_", " ").title(),
            query=item.query,
            report=item.explanation,
            type=item.chart_type,
            relevance=item.relevance,
            is_time_based=item.is_time_based,
            chart_type=item.chart_type,
            is_user_generated=False
        )
        db.add(chart)
        charts.append(chart)
    db.commit()
    return charts
  
async def post_to_llm(url: str, payload: dict) -> Any:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as e:
        raise Exception(f"Error communicating with service at {url}: {str(e)}")
    except httpx.HTTPStatusError as e:
        raise Exception(f"Bad response from {url}: {str(e.response.status_code)} - {str(e.response.text)}")