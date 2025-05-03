"""
This module contains functions to generate and
store charts based on user input and database connections.

It includes functions to post data to an LLM service,
generate SQL queries, and execute those queries on an external database.

It also includes a function to transform the data returned from the database
into a specific format.
"""

import json
from typing import Any
from uuid import UUID

import httpx
import sqlalchemy
from fastapi import Depends, HTTPException, status
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.models.schema_models import ChartModel, DatabaseConnectionModel
from app.schemas import QueryRequest
from app.utils.constants import LLM_SERVICE_URL, LLM_SPREADSHEET_URL
from app.utils.crypt import decrypt_string
from app.utils.sample_data import get_sample_data
from app.utils.token_parser import get_current_user

# LLM_SERVICE_URL = "http://localhost:8001/queries/"


async def post_to_llm(url: str, payload: dict) -> Any:
    """
    Posts data to the LLM service and returns the response.
    :param url: The URL of the LLM service.
    :param payload: The data to be sent to the LLM service.
    :return: The response from the LLM service.
    """
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as e:
        raise httpx.RequestError(
            f"Error communicating with LLM service at {url}: {str(e)}"
        ) from e
    except httpx.HTTPStatusError as e:
        raise httpx.HTTPStatusError(
            f"LLM service error: {str(e.response.status_code)} - {str(e.response.text)}",
            request=e.request,
            response=e.response,
        ) from e


async def generate_and_store_charts(
    db: Session,
    datasource_connection_id: UUID,
    project_id: UUID,
    query_request: QueryRequest,
    token_payload: dict = Depends(get_current_user),
):
    """
    Generates SQL queries based on user input and stores the charts in the database.
    :param db: The database session.
    :param datasource_connection_id: The ID of the database connection.
    :param project_id: The ID of the project.
    :param query_request: The request object containing user input.
    :param token_payload: The token payload containing user information.
    :return: A list of generated charts.
    """
    db_conn = (
        db.query(DatabaseConnectionModel)
        .filter_by(id=datasource_connection_id, project_id=project_id)
        .first()
    )
    if not db_conn:
        raise HTTPException(
            status_code=404,
            detail="No database connection found for this project or db connection not found",
        )

    decrypt_conn_string = decrypt_string(db_conn.db_connection_string)

    user_id_str = token_payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )

    try:
        user_id = UUID(user_id_str)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format in token",
        ) from exc
    sample_data = None
    if db_conn.consent_given:
        sample_data = get_sample_data(decrypt_conn_string)
    db_schema = json.loads(db_conn.db_schema)
    print(query_request.db_type)
    llm_payload = {
        "db_schema": db_conn.db_schema,
        "db_type": query_request.db_type,
        "role": query_request.role,
        "domain": query_request.domain,
        "min_date": db_schema.get("min_date"),
        "max_date": db_schema.get("max_date"),
        "api_key": query_request.api_key,
        "sample_data": sample_data or "",
    }

    if db_conn.db_type == "spreadsheet":
        llm_response_spreadsheet = await post_to_llm(LLM_SPREADSHEET_URL, llm_payload)
        queries = llm_response_spreadsheet.get("queries", [])
    else:
        llm_response = await post_to_llm(LLM_SERVICE_URL, llm_payload)
        queries = llm_response.get("queries", [])
    print(queries)

    chart_models = []
    for q in queries:
        chart = ChartModel(
            title=q["explanation"],
            query=q["query"],
            report=q["explanation"],
            type=q["chart_type"],
            relevance=q["relevance"],
            is_time_based=q["is_time_based"],
            chart_type=q["chart_type"],
            is_user_generated=False,
            created_by=user_id,
        )
        #     db.add(chart)
        #     db.flush()

        # assoc = DashboardChartsModel(
        #     chart_id=chart.id,
        #     dashboard_id=dashboard_id,
        # )
        # db.add(assoc)
        chart_models.append(chart)

    db.commit()
    return chart_models


def execute_external_query(
    db: Session,
    datasource_connection_id: UUID,
    query_input: str,
    token_payload: dict = Depends(get_current_user),
):
    """
    Executes a SQL query on the external database.
    """
    user_id_str = token_payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )

    try:
        user_id = UUID(user_id_str)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format in token",
        ) from exc

    # generated_query = db.query(ChartModel).filter(ChartModel.id == query_id).first()
    # if not generated_query:
    #     raise HTTPException(status_code=404, detail="Query not found")
    query = query_input

    datasource_connection_id = (
        db.query(DatabaseConnectionModel).filter_by(id=datasource_connection_id).first()
    )
    if not datasource_connection_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Datasource Connection ID dosent Exist",
        )

    decrypt_conn_string = decrypt_string(datasource_connection_id.db_connection_string)
    engine = create_engine(decrypt_conn_string)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        print(query)
        result = session.execute(text(query))
        data = result.fetchall()
        print(data)
        response = [dict(row._mapping) for row in data]  # Convert result to dictionary
        transformed_data = transform_data_dynamic(response)
        print(transformed_data)
        response = {
            "result": transformed_data["data"],
            "x_axis": transformed_data["x_axis"],
            "y_axis": transformed_data["y_axis"],
            # "id": str(generated_query.id),
            # "chartType": generated_query.chart_type,
            # "report": generated_query.report
        }
        print(response)
        return response
    except (sqlalchemy.exc.SQLAlchemyError, ValueError) as e:
        return {"error": str(e)}
    finally:
        session.close()
        engine.dispose()


def transform_data_dynamic(data):
    """
    Transforms an array of dictionaries into the required format by dynamically detecting fields.
    Also returns the detected x-axis and y-axis labels.

    :param data: List of dictionaries with unknown key names
    :return: Dictionary containing transformed data and axis labels
    """
    if not data:
        return {"data": [], "x_axis": None, "y_axis": None}

    keys = list(data[0].keys())

    if len(keys) < 2:
        raise ValueError(
            "Data must contain at least two fields (one for label and one for value)."
        )

    x_axis = keys[0]  # First key for x-axis
    y_axis = keys[1]  # Second key for y-axis

    transformed_data = [
        {"label": str(item[x_axis]), "value": item[y_axis]} for item in data
    ]

    return {"data": transformed_data, "x_axis": x_axis, "y_axis": y_axis}
