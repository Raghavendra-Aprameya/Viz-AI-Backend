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
import logging

logger = logging.getLogger(__name__)

# LLM_SERVICE_URL = "http://localhost:8001/queries/"

from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import text, create_engine
from fastapi import HTTPException, status, Depends
from uuid import UUID
from typing import Any
import httpx
import json
from app.models.schema_models import (
    ChartModel,
    DashboardChartsModel,
    DatabaseConnectionModel,
)
from app.schemas import QueryRequest
from app.utils.token_parser import get_current_user
from app.utils.crypt import decrypt_string
from app.utils.constants import LLM_SERVICE_URL, LLM_SPREADSHEET_URL
from app.utils.sample_data import get_sample_data


# celery -A app.utils.tasks.celery_app worker --loglevel=info
# celery -A app.utils.tasks.celery_app worker --loglevel=info
async def post_to_llm(url: str, payload: dict) -> Any:
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as e:
        raise Exception(f"Error communicating with LLM service at {url}: {str(e)}")
    except httpx.HTTPStatusError as e:
        raise Exception(
            f"LLM service error: {str(e.response.status_code)} - {str(e.response.text)}"
        )


async def generate_and_store_charts(
    db: Session,
    datasource_connection_id: UUID,
    project_id: UUID,
    query_request: QueryRequest,
    token_payload: dict = Depends(get_current_user),
):
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
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid UUID format in token",
        )
    sample_data = None
    if db_conn.consent_given:
        sample_data = get_sample_data(decrypt_conn_string)
    db_schema = json.loads(db_conn.db_schema)
    logger.debug(f"Processing database connection: {db_conn.connection_name}, type: {db_conn.db_type}")
    llm_payload = {
        "db_schema": db_conn.db_schema,
        "db_type": db_conn.db_type,
        "role": query_request.role,
        "domain": query_request.domain,
        "min_date": query_request.min_date,
        "max_date": query_request.max_date,
        "api_key": query_request.api_key,
        "sample_data": sample_data or "",
    }

    if db_conn.db_type == "spreadsheet":
        llm_response_spreadsheet = await post_to_llm(LLM_SPREADSHEET_URL, llm_payload)
        queries = llm_response_spreadsheet.get("queries", [])
    else:
        llm_response = await post_to_llm(LLM_SERVICE_URL, llm_payload)
        queries = llm_response.get("queries", [])
    logger.debug(f"Generated {len(queries)} queries from LLM")

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


def replace_dates_in_query(query: str, from_date: str = None, to_date: str = None) -> str:
    """
    Replaces date literals and bind parameters in a SQL query with provided from_date and to_date values.
    If dates are not provided, keeps the original dates in the query.
    
    Args:
        query: The original SQL query
        from_date: Start date in YYYY-MM-DD format to replace the first date found
        to_date: End date in YYYY-MM-DD format to replace the second date found
    
    Returns:
        Modified SQL query with dates replaced if provided, otherwise original query
    """
    import re
    
    # First, handle SQLAlchemy bind parameters (:from_date, :to_date)
    if from_date:
        # Replace :from_date bind parameter with actual date value
        # Handle both :from_date and :from_date in TO_DATE functions
        query = re.sub(
            r':from_date',
            f"'{from_date}'",
            query,
            flags=re.IGNORECASE
        )
    
    if to_date:
        # Replace :to_date bind parameter with actual date value
        query = re.sub(
            r':to_date',
            f"'{to_date}'",
            query,
            flags=re.IGNORECASE
        )
    
    # If no dates provided, return query (bind parameters will remain, but that's handled by error)
    if not from_date and not to_date:
        return query
    
    # Then handle date literals in SQL (handles both single and double quotes)
    # Matches dates in format: 'YYYY-MM-DD' or "YYYY-MM-DD"
    date_pattern = r"(['\"])(\d{4}-\d{2}-\d{2})\1"
    
    # Find all date matches in the query
    matches = list(re.finditer(date_pattern, query))
    
    if not matches:
        # No date literals found in query, return as is (bind params already handled)
        return query
    
    # Build list of replacements (position, new_value, quote_char)
    # Replace from the end to preserve correct positions
    replacements = []
    
    if len(matches) >= 2:
        # Two or more dates found: first with from_date, second with to_date
        if to_date:
            last_match = matches[-1]
            replacements.append((last_match.start(), last_match.end(), 
                               f"{last_match.group(1)}{to_date}{last_match.group(1)}"))
        if from_date:
            first_match = matches[0]
            replacements.append((first_match.start(), first_match.end(),
                               f"{first_match.group(1)}{from_date}{first_match.group(1)}"))
    elif len(matches) == 1:
        # Only one date found
        match = matches[0]
        quote_char = match.group(1)
        if from_date:
            replacements.append((match.start(), match.end(), f"{quote_char}{from_date}{quote_char}"))
        elif to_date:
            replacements.append((match.start(), match.end(), f"{quote_char}{to_date}{quote_char}"))
    
    # Apply replacements from right to left (end to beginning) to preserve positions
    modified_query = query
    for start, end, replacement in sorted(replacements, reverse=True):
        modified_query = modified_query[:start] + replacement + modified_query[end:]
    
    return modified_query


def add_date_filter_to_query(query: str, from_date: str = None, to_date: str = None) -> str:
    """
    Adds date filtering to a SQL query by detecting date columns and adding WHERE clauses.
    
    Args:
        query: The original SQL query
        from_date: Start date in YYYY-MM-DD format
        to_date: End date in YYYY-MM-DD format
    
    Returns:
        Modified SQL query with date filtering applied
    """
    if not from_date and not to_date:
        return query
    
    import re
    
    # Common date column names to check for (in order of preference)
    date_column_names = [
        'date', 'created_at', 'updated_at', 'timestamp', 'created_date',
        'updated_date', 'transaction_date', 'record_date', 'event_date', 'occurred_at'
    ]
    
    # Normalize query for case-insensitive matching
    query_upper = query.upper()
    
    # Find the first date column that appears in the query
    date_column = None
    for col_name in date_column_names:
        # Look for the column name as a word boundary
        pattern = r'\b' + re.escape(col_name) + r'\b'
        if re.search(pattern, query_upper, re.IGNORECASE):
            # Get the actual case from the original query
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                date_column = match.group()
                break
    
    if not date_column:
        # If no date column found, return original query without modification
        return query
    
    # Build WHERE conditions
    conditions = []
    if from_date:
        conditions.append(f"{date_column} >= '{from_date}'")
    if to_date:
        conditions.append(f"{date_column} <= '{to_date} 23:59:59'")
    
    where_clause = " AND ".join(conditions)
    
    # Check if query already has WHERE clause
    if re.search(r'\bWHERE\b', query_upper):
        # Add to existing WHERE clause - find the end of WHERE clause
        # Look for WHERE and then find where it ends (before GROUP BY, ORDER BY, LIMIT, etc.)
        where_match = re.search(r'\bWHERE\b', query_upper)
        if where_match:
            where_start = where_match.end()
            # Find the end of the WHERE clause
            where_end = len(query)
            for keyword in ['GROUP BY', 'ORDER BY', 'LIMIT', 'HAVING']:
                pos = query_upper.find(keyword, where_start)
                if pos != -1:
                    where_end = min(where_end, pos)
            
            # Insert the new condition
            query = query[:where_end].rstrip() + f" AND {where_clause} " + query[where_end:]
    else:
        # Add new WHERE clause before GROUP BY, ORDER BY, LIMIT, HAVING
        insert_pos = len(query)
        for keyword in ['GROUP BY', 'ORDER BY', 'LIMIT', 'HAVING']:
            pos = query_upper.find(keyword)
            if pos != -1:
                insert_pos = min(insert_pos, pos)
        
        # Insert WHERE clause
        query = query[:insert_pos].rstrip() + f" WHERE {where_clause} " + query[insert_pos:]
    
    return query


def execute_external_query(
    db: Session,
    datasource_connection_id: UUID,
    query_input: str,
    token_payload: dict,
    from_date: str = None,
    to_date: str = None,
):
    """
    Executes a SQL query on the external database.
    
    Args:
        db: Database session
        datasource_connection_id: Connection ID
        query_input: SQL query to execute
        token_payload: User authentication payload
        from_date: Optional start date for filtering (YYYY-MM-DD format)
        to_date: Optional end date for filtering (YYYY-MM-DD format)
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
    
    # Check if query contains bind parameters that require dates
    import re
    has_from_date_param = bool(re.search(r':from_date\b', query_input, re.IGNORECASE))
    has_to_date_param = bool(re.search(r':to_date\b', query_input, re.IGNORECASE))
    
    # If query has bind parameters but dates are not provided, raise an error
    if (has_from_date_param and not from_date) or (has_to_date_param and not to_date):
        missing_params = []
        if has_from_date_param and not from_date:
            missing_params.append("from_date")
        if has_to_date_param and not to_date:
            missing_params.append("to_date")
        raise ValueError(
            f"Query contains bind parameters ({', '.join(missing_params)}) but corresponding date values were not provided. "
            f"Please provide {'from_date' if has_from_date_param and not from_date else ''} "
            f"{'and ' if has_from_date_param and not from_date and has_to_date_param and not to_date else ''}"
            f"{'to_date' if has_to_date_param and not to_date else ''} in the request."
        )
    
    # Replace dates in query if provided, otherwise use default dates in query
    query = replace_dates_in_query(query_input, from_date, to_date)

    datasource_connection_id = (
        db.query(DatabaseConnectionModel).filter_by(id=datasource_connection_id).first()
    )
    if not datasource_connection_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Datasource Connection ID dosent Exist",
        )

    decrypt_conn_string = decrypt_string(datasource_connection_id.db_connection_string)

    # Use external engine manager for connection pooling
    from app.core.db import external_engine_manager
    engine = external_engine_manager.get_engine(
        connection_id=datasource_connection_id.id,
        connection_string=decrypt_conn_string,
        db_type=datasource_connection_id.db_type
    )

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        logger.debug(f"Executing query: {query[:200]}..." if len(query) > 200 else f"Executing query: {query}")
        result = session.execute(text(query))
        data = result.fetchall()
        response = [dict(row._mapping) for row in data]
        transformed_data = transform_data_dynamic(response)
        response = {
            "result": transformed_data["data"],
            "x_axis": transformed_data["x_axis"],
            "y_axis": transformed_data["y_axis"],
        }
        logger.debug(f"Query executed successfully, returned {len(response['result'])} rows")
        return response
    except (sqlalchemy.exc.SQLAlchemyError, ValueError) as e:
        logger.error(f"Query execution failed for connection {datasource_connection_id}: {str(e)}", exc_info=True)
        return {"error": str(e)}
    finally:
        session.close()
        # Engine is managed by external_engine_manager, no dispose() needed


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
