import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.schema_models import UserProjectRoleModel,DatabaseConnectionModel,ChartModel
from app.schemas import Nl2SQLChartResponse,Nl2SQLChatRequest
from uuid import UUID
import logging

logger = logging.getLogger(__name__)

async def generate_nl_sql_and_save(
    data: Nl2SQLChatRequest,
    db: Session,
    user_id: UUID,
    llm_endpoint: str = "http://127.0.0.1:8000/queries/convert_nl_to_sql/"
):
    try:
        user_roles = db.query(UserProjectRoleModel).filter_by(user_id=user_id).all()
        if not user_roles:
            raise HTTPException(status_code=403, detail="User has no project roles assigned.")

        db_conn = None
        for role in user_roles:
            db_conn = db.query(DatabaseConnectionModel).filter_by(project_id=role.project_id).first()
            if db_conn:
                break

        if not db_conn:
            raise HTTPException(status_code=404, detail="No database connection found for user's projects.")

        schema_str = db_conn.db_schema or "{}"


        payload = {
            "nl_query": data.nl_query,
            "db_schema": schema_str,
            "db_type": "postgresql", 
            "api_key": getattr(data, "api_key", None)
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(llm_endpoint, json=payload)
            response.raise_for_status()
            llm_result = response.json()

        sql_query = llm_result.get("sql_query")
        if not sql_query:
            raise HTTPException(status_code=400, detail="LLM did not return SQL query.")

        # 3. Save chart
        new_chart = ChartModel(
            title="Generated Chart",
            query=sql_query,
            report=llm_result.get("explanation", "Auto-generated"),
            type="sql",
            relevance=llm_result.get("relevance", 1.0),
            is_time_based=llm_result.get("is_time_based", False),
            chart_type=llm_result.get("chart_type", "unknown"),
            is_user_generated=True
        )

        db.add(new_chart)
        db.commit()

        return {
            "status": "success",
            "sql_query": sql_query,
            "chart_id": str(new_chart.id)
        }

    except httpx.HTTPStatusError as e:
        logger.error("LLM service error: %s", e.response.text)
        raise HTTPException(status_code=e.response.status_code, detail=f"LLM error: {e.response.text}")
    except httpx.RequestError as e:
        logger.error("LLM request failed: %s", str(e))
        raise HTTPException(status_code=500, detail=f"LLM request failed: {str(e)}")
    except Exception as e:
        logger.exception("Failed to generate/save SQL query")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
