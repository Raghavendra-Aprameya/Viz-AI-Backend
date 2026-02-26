"""
SOQL Executor

Executes SOQL queries against Salesforce using the simple-salesforce library.
Handles pagination, date placeholder replacement, and transforms results
into the standard VizAI response format.

This module provides functions to:
- Execute SOQL queries with automatic pagination
- Replace date placeholders in SOQL queries
- Transform Salesforce query results to the standard chart data format
"""

import re
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
from uuid import UUID
from datetime import datetime

if TYPE_CHECKING:
    from app.models.schema_models import DatabaseConnectionModel

try:
    from simple_salesforce import Salesforce
    from simple_salesforce.exceptions import SalesforceMalformedRequest
except ImportError:
    raise ImportError(
        "simple-salesforce is required for Salesforce integration. "
        "Install it with: pip install simple-salesforce"
    )

from app.services.salesforce_client import salesforce_client_manager

logger = logging.getLogger(__name__)


# Salesforce DateTime fields require YYYY-MM-DDThh:mm:ssZ; Date fields require YYYY-MM-DD
# ConvertedDate (Lead) is Date type; ClosedDate (Case) is DateTime type
_SOQL_DATETIME_FIELDS = (
    "CreatedDate",
    "LastModifiedDate",
    "SystemModStamp",
    "LastActivityDate",
    "EmailBouncedDate",
    "LastViewedDate",
    "LastReferencedDate",
    "ClosedDate",  # Case.ClosedDate is DateTime
)


def replace_soql_date_placeholders(
    query: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> str:
    """
    Replace date placeholders in SOQL query with actual dates.

    SOQL uses:
    - YYYY-MM-DD for Date fields (e.g., CloseDate, ActivityDate)
    - YYYY-MM-DDThh:mm:ssZ for DateTime fields (e.g., CreatedDate, LastModifiedDate)

    We detect if the query filters on a DateTime field and use the correct format.

    Args:
        query: SOQL query string with [MIN_DATE] and [MAX_DATE] placeholders
        from_date: Start date in YYYY-MM-DD format
        to_date: End date in YYYY-MM-DD format

    Returns:
        SOQL query with date placeholders replaced
    """
    def _normalize_date(date_str: str) -> str:
        if not date_str:
            return date_str
        if "T" in date_str:
            date_str = date_str.split("T")[0]
        if "Z" in date_str:
            date_str = date_str.split("Z")[0]
            if "T" in date_str:
                date_str = date_str.split("T")[0]
        return date_str

    def _to_datetime(date_str: str, end_of_day: bool = False) -> str:
        d = _normalize_date(date_str)
        if not d:
            return date_str
        if end_of_day:
            return f"{d}T23:59:59Z"
        return f"{d}T00:00:00Z"

    # Check if query uses a DateTime field with our placeholders (e.g. CreatedDate >= [MIN_DATE])
    query_upper = query.upper()
    use_datetime_format = any(
        fld.upper() in query_upper
        for fld in _SOQL_DATETIME_FIELDS
    ) and ("[MIN_DATE]" in query or "[MAX_DATE]" in query)

    if from_date:
        from_val = _to_datetime(from_date, end_of_day=False) if use_datetime_format else _normalize_date(from_date)
        query = query.replace("[MIN_DATE]", from_val)
        query = re.sub(r":from_date\b", from_val, query, flags=re.IGNORECASE)

    if to_date:
        to_val = _to_datetime(to_date, end_of_day=True) if use_datetime_format else _normalize_date(to_date)
        query = query.replace("[MAX_DATE]", to_val)
        query = re.sub(r":to_date\b", to_val, query, flags=re.IGNORECASE)

    return query


def execute_soql_query(
    sf_client: Salesforce,
    query: str,
    include_deleted: bool = False,
) -> Dict[str, Any]:
    """
    Execute a SOQL query and return results with automatic pagination.

    Args:
        sf_client: Salesforce client instance
        query: SOQL query string
        include_deleted: Whether to include deleted records (queryAll)

    Returns:
        Dict containing:
        - records: List of record dictionaries
        - totalSize: Total number of records
        - done: Whether all records have been fetched

    Raises:
        SalesforceMalformedRequest: If the SOQL query is invalid
    """
    logger.debug(f"Executing SOQL query: {query[:200]}..." if len(query) > 200 else f"Executing SOQL: {query}")

    try:
        if include_deleted:
            result = sf_client.query_all(query)
        else:
            result = sf_client.query(query)

        records = result.get("records", [])
        total_size = result.get("totalSize", 0)
        done = result.get("done", True)

        # Handle pagination if not all records retrieved
        while not done:
            next_url = result.get("nextRecordsUrl")
            if next_url:
                result = sf_client.query_more(next_url, identifier_is_url=True)
                records.extend(result.get("records", []))
                done = result.get("done", True)
            else:
                break

        logger.debug(f"SOQL query returned {len(records)} records (total: {total_size})")

        return {
            "records": records,
            "totalSize": total_size,
            "done": True,
        }

    except SalesforceMalformedRequest as e:
        logger.error(f"SOQL query error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error executing SOQL: {e}", exc_info=True)
        raise


def transform_salesforce_result(
    records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Transform Salesforce query results to the standard VizAI chart data format.

    Salesforce returns records with nested attributes object that needs to be stripped.

    Args:
        records: List of Salesforce record dictionaries

    Returns:
        Dict containing:
        - data: List of {label, value} dicts for charting
        - x_axis: Name of the x-axis field
        - y_axis: Name of the y-axis field
    """
    if not records:
        return {"data": [], "x_axis": None, "y_axis": None}

    # Clean records by removing Salesforce metadata (attributes field)
    cleaned_records = []
    for record in records:
        cleaned = {}
        for key, value in record.items():
            if key == "attributes":
                continue
            # Handle nested relationship queries (e.g., Account.Name)
            if isinstance(value, dict) and "attributes" in value:
                # Extract nested object fields
                for nested_key, nested_value in value.items():
                    if nested_key != "attributes":
                        cleaned[f"{key}.{nested_key}"] = nested_value
            else:
                cleaned[key] = value
        cleaned_records.append(cleaned)

    if not cleaned_records:
        return {"data": [], "x_axis": None, "y_axis": None}

    # Get field names from first record
    keys = list(cleaned_records[0].keys())

    # Handle single-column queries (e.g., COUNT())
    if len(keys) == 1:
        y_axis = keys[0]
        transformed_data = [
            {"label": str(idx + 1), "value": item.get(y_axis)}
            for idx, item in enumerate(cleaned_records)
        ]
        return {
            "data": transformed_data,
            "x_axis": "Index",
            "y_axis": y_axis,
        }

    # Handle multi-column queries
    if len(keys) < 2:
        return {"data": [], "x_axis": None, "y_axis": None}

    x_axis = keys[0]
    y_axis = keys[1]

    transformed_data = [
        {"label": str(item.get(x_axis, "")), "value": item.get(y_axis)}
        for item in cleaned_records
    ]

    return {
        "data": transformed_data,
        "x_axis": x_axis,
        "y_axis": y_axis,
    }


def execute_salesforce_query(
    connection_id: UUID,
    session_id: str,
    instance_url: str,
    query: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute a SOQL query against Salesforce and return formatted results.

    This is the main entry point for executing Salesforce queries.
    Uses OAuth2 session-based authentication only.

    Args:
        connection_id: UUID of the database connection
        session_id: Salesforce OAuth access_token
        instance_url: Salesforce instance URL (e.g., https://na45.salesforce.com)
        query: SOQL query string (may contain date placeholders)
        from_date: Start date for placeholder replacement (YYYY-MM-DD)
        to_date: End date for placeholder replacement (YYYY-MM-DD)

    Returns:
        Dict containing:
        - result: List of {label, value} dicts
        - x_axis: X-axis field name
        - y_axis: Y-axis field name

        Or on error:
        - error: Error message string
    """
    try:
        # Get or create Salesforce client using OAuth2
        sf_client = salesforce_client_manager.get_client(
            connection_id=connection_id,
            session_id=session_id,
            instance_url=instance_url,
        )

        # Replace date placeholders in query
        processed_query = replace_soql_date_placeholders(query, from_date, to_date)

        # Execute SOQL query
        result = execute_soql_query(sf_client, processed_query)

        # Transform results to standard format
        transformed = transform_salesforce_result(result.get("records", []))

        return {
            "result": transformed["data"],
            "x_axis": transformed["x_axis"],
            "y_axis": transformed["y_axis"],
        }

    except SalesforceMalformedRequest as e:
        error_msg = f"Invalid SOQL query: {str(e)}"
        logger.error(error_msg)
        return {"error": error_msg}

    except Exception as e:
        error_msg = f"Salesforce query execution failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"error": error_msg}


def _clean_salesforce_records_for_insights(
    records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Clean Salesforce records for insights: remove attributes, flatten nested
    relationship data, and ensure all values are JSON-serializable.
    Returns raw row data (list of flat dicts) compatible with insight analysis.
    """
    cleaned_records = []
    for record in records:
        cleaned = {}
        for key, value in record.items():
            if key == "attributes":
                continue
            if isinstance(value, dict) and "attributes" in value:
                for nested_key, nested_value in value.items():
                    if nested_key != "attributes":
                        cleaned[f"{key}.{nested_key}"] = (
                            str(nested_value) if nested_value is not None and not isinstance(
                                nested_value, (str, int, float, bool)
                            ) else nested_value
                        )
            elif value is None:
                cleaned[key] = None
            elif isinstance(value, (int, float, str, bool)):
                cleaned[key] = value
            else:
                cleaned[key] = str(value)
        cleaned_records.append(cleaned)
    return cleaned_records


async def execute_salesforce_kpi_queries(
    db_connection: "DatabaseConnectionModel",
    queries: List[Dict[str, str]],
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Execute KPI SOQL queries against Salesforce and return results in the same
    format as execute_kpi_queries for compatibility with generate_insights_from_results.

    Args:
        db_connection: DatabaseConnectionModel (Salesforce connection)
        queries: List of {kpi_title, description, sql_query} (sql_query contains SOQL)
        from_date: Start date for [MIN_DATE] placeholder (YYYY-MM-DD)
        to_date: End date for [MAX_DATE] placeholder (YYYY-MM-DD)

    Returns:
        List of {kpi_title, description, query, success, data, row_count} or
        {..., error} on failure - same format as execute_kpi_queries
    """
    from datetime import datetime, timedelta
    from app.utils.crypt import decrypt_string

    # Default date range: last 6 months
    if not from_date or not to_date:
        today = datetime.utcnow().date()
        default_from = (today - timedelta(days=183)).isoformat()
        default_to = today.isoformat()
        from_date = from_date or default_from
        to_date = to_date or default_to

    decrypted_session_id = (
        decrypt_string(db_connection.db_password) if db_connection.db_password else ""
    )
    instance_url = db_connection.db_host_link or ""

    if not decrypted_session_id or not instance_url:
        raise ValueError(
            "Salesforce connection missing OAuth credentials (session_id, instance_url)"
        )

    try:
        sf_client = salesforce_client_manager.get_client(
            connection_id=db_connection.id,
            session_id=decrypted_session_id,
            instance_url=instance_url,
        )
    except Exception as e:
        logger.error(f"Failed to get Salesforce client: {e}")
        raise

    logger.info("Executing %d KPI queries (Salesforce)", len(queries))
    results = []
    for kpi in queries:
        query = kpi.get("sql_query", kpi.get("query", ""))
        if not query:
            results.append({
                "kpi_title": kpi["kpi_title"],
                "description": kpi["description"],
                "query": "",
                "success": False,
                "error": "No query provided",
                "data": [],
                "row_count": 0,
            })
            continue
        try:
            processed_query = replace_soql_date_placeholders(
                query, from_date=from_date, to_date=to_date
            )
            logger.debug(
                f"Executing SOQL for KPI: {kpi['kpi_title']}"
            )
            result = execute_soql_query(sf_client, processed_query)
            records = result.get("records", [])
            cleaned_data = _clean_salesforce_records_for_insights(records)
            results.append({
                "kpi_title": kpi["kpi_title"],
                "description": kpi["description"],
                "query": query,
                "success": True,
                "data": cleaned_data,
                "row_count": len(cleaned_data),
            })
        except Exception as query_error:
            logger.error(f"SOQL error for KPI {kpi['kpi_title']}: {query_error}")
            results.append({
                "kpi_title": kpi["kpi_title"],
                "description": kpi["description"],
                "query": query,
                "success": False,
                "error": str(query_error),
                "data": [],
                "row_count": 0,
            })

    successful = sum(1 for r in results if r["success"])
    logger.info("Executed %d/%d KPI queries successfully (Salesforce)", successful, len(queries))
    return results


def get_salesforce_sample_data(
    sf_client: Salesforce,
    object_name: str,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Get sample data from a Salesforce object for query generation context.

    Args:
        sf_client: Salesforce client instance
        object_name: Salesforce object API name (e.g., "Account", "Contact")
        limit: Maximum number of records to return

    Returns:
        List of sample record dictionaries
    """
    try:
        # Get object description to find queryable fields
        desc = sf_client.__getattr__(object_name).describe()

        # Get first few string/text fields for sampling
        sample_fields = []
        for field in desc.get("fields", [])[:10]:
            if field.get("type") in ("string", "textarea", "picklist", "id"):
                sample_fields.append(field.get("name"))

        if not sample_fields:
            sample_fields = ["Id"]

        # Build and execute sample query
        fields_str = ", ".join(sample_fields[:5])
        query = f"SELECT {fields_str} FROM {object_name} LIMIT {limit}"

        result = sf_client.query(query)

        # Clean records
        records = []
        for record in result.get("records", []):
            cleaned = {k: v for k, v in record.items() if k != "attributes"}
            records.append(cleaned)

        return records

    except Exception as e:
        logger.warning(f"Failed to get sample data for {object_name}: {e}")
        return []
