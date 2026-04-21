# from sqlalchemy import create_engine, inspect

# from datetime import datetime, timedelta
# from app.utils.crypt import decrypt_string

# def get_schema_structure(connection_string: str):
#     engine = create_engine(connection_string)
#     inspector = inspect(engine)

#     schema_info = {"tables": []}
#     # max_date = datetime.now().date()
#     # min_date = max_date - timedelta(days=183) 
#     min_date= datetime.fromisoformat("2003-01-06")
#     max_date= datetime.fromisoformat("2005-06-11")

#     try:
#         with engine.connect() as connection:
#             for table_name in inspector.get_table_names():
#                 columns = inspector.get_columns(table_name)
#                 primary_keys = inspector.get_pk_constraint(table_name)
#                 foreign_keys = [
#                     {"column": fk["constrained_columns"][0], "references": fk["referred_table"]}
#                     for fk in inspector.get_foreign_keys(table_name)
#                 ]

#                 schema_info["tables"].append({
#                     "name": table_name,
#                     "columns": [
#                         {"name": col["name"], "type": str(col["type"])}
#                         for col in columns
#                     ],
#                     "primary_keys": primary_keys,
#                     "foreign_keys": foreign_keys
#                 })

#         schema_info["min_date"] = min_date.isoformat()
#         schema_info["max_date"] = max_date.isoformat()
#         print(f"Database Date Range: Min Date: {min_date}, Max Date: {max_date}")

#     except Exception as e:
#         print(f"Error fetching schema information: {e}. Returning schema info with default date range.")
#         schema_info["min_date"] = None
#         schema_info["max_date"] = None

#     return schema_info

# blocking sync function — runs in a thread
from sqlalchemy import create_engine, inspect, text
from datetime import datetime
from typing import Optional, Dict, Any, List
import json
import logging
import re
from urllib.parse import urlparse, parse_qs

try:
    from simple_salesforce import Salesforce
    from simple_salesforce.exceptions import SalesforceAuthenticationFailed
    SALESFORCE_AVAILABLE = True
except ImportError:
    SALESFORCE_AVAILABLE = False

# Set up logger
logger = logging.getLogger(__name__)

# ---- get_schema_structure (blocking; run in thread) ----
def get_schema_structure(connection_string: str, queue, loop):
    engine = None
    schema_info = {"tables": []}
    min_date = datetime.fromisoformat("2003-01-06")
    max_date = datetime.fromisoformat("2005-06-11")

    try:
        # Parse connection string to detect database type
        parsed_url = urlparse(connection_string)
        is_oracle = parsed_url.scheme and "oracle" in parsed_url.scheme.lower()
        is_databricks = parsed_url.scheme and "databricks" in parsed_url.scheme.lower()
        oracle_schema = parsed_url.username if is_oracle else None
        query_params = parse_qs(parsed_url.query or "")
        databricks_catalog = (query_params.get("catalog", [None])[0] or "").strip() if is_databricks else ""
        databricks_schema = (query_params.get("schema", [None])[0] or "").strip() if is_databricks else ""
        
        if is_databricks:
            logger.info(
                "Starting schema extraction - DB Type: Databricks, Catalog: %s, Schema: %s",
                databricks_catalog,
                databricks_schema,
            )
        else:
            logger.info(f"Starting schema extraction - DB Type: {'Oracle' if is_oracle else 'Other'}, Schema: {oracle_schema}")
        
        engine = create_engine(connection_string, pool_pre_ping=True)
        inspector = inspect(engine)
        
        logger.info("Engine created successfully, connecting to database...")

        with engine.connect() as connection:
            logger.info("Database connection established")
            
            # Databricks: use information_schema to preserve 3-level namespace
            if is_databricks:
                if not databricks_catalog or not databricks_schema:
                    error_msg = "Databricks connection string is missing catalog or schema query parameters."
                    logger.error(error_msg)
                    loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "message": error_msg})
                    raise Exception(error_msg)
                if not re.match(r"^[A-Za-z0-9_]+$", databricks_catalog):
                    raise Exception("Invalid Databricks catalog name format")
                if not re.match(r"^[A-Za-z0-9_]+$", databricks_schema):
                    raise Exception("Invalid Databricks schema name format")

                tables_sql = text(
                    f"""
                    SELECT table_catalog, table_schema, table_name
                    FROM {databricks_catalog}.information_schema.tables
                    WHERE table_schema = :schema_name
                      AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                    """
                )
                table_rows = connection.execute(tables_sql, {"schema_name": databricks_schema}).mappings().all()
                table_names = [r.get("table_name") for r in table_rows]
                logger.info(
                    "Found %d Databricks tables in %s.%s",
                    len(table_names),
                    databricks_catalog,
                    databricks_schema,
                )
            # For Oracle, try with schema first
            elif is_oracle and oracle_schema:
                logger.info(f"Oracle detected, trying to get tables from schema: {oracle_schema.upper()}")
                try:
                    table_names = inspector.get_table_names(schema=oracle_schema.upper())
                    logger.info(f"Found {len(table_names)} tables using schema '{oracle_schema.upper()}'")
                    if not table_names:
                        logger.warning(f"No tables found with schema '{oracle_schema.upper()}', trying without schema...")
                        table_names = inspector.get_table_names()
                        logger.info(f"Found {len(table_names)} tables without schema")
                except Exception as schema_error:
                    logger.warning(f"Error getting tables with schema '{oracle_schema.upper()}': {schema_error}, trying without schema...")
                    table_names = inspector.get_table_names()
                    logger.info(f"Found {len(table_names)} tables without schema")
            else:
                table_names = inspector.get_table_names()
                logger.info(f"Found {len(table_names)} tables")

            total_tables = len(table_names)

            if total_tables == 0:
                error_msg = "No tables found in database"
                logger.error(error_msg)
                if is_oracle:
                    error_msg += f". For Oracle, ensure schema '{oracle_schema}' is correct and has tables."
                loop.call_soon_threadsafe(queue.put_nowait, {
                    "type": "error",
                    "message": error_msg
                })
                raise Exception(error_msg)

            # Immediately inform WS of total tables (frontend can show ETA)
            loop.call_soon_threadsafe(queue.put_nowait, {
                "type": "started",
                "totalTables": total_tables,
                "message": f"Found {total_tables} tables"
            })

            logger.info(f"Starting to extract {total_tables} tables...")

            for idx, table_name in enumerate(table_names, start=1):
                try:
                    logger.debug(f"Extracting table {idx}/{total_tables}: {table_name}")

                    # Databricks column extraction from information_schema
                    if is_databricks:
                        columns_sql = text(
                            f"""
                            SELECT column_name, data_type
                            FROM {databricks_catalog}.information_schema.columns
                            WHERE table_schema = :schema_name
                              AND table_name = :table_name
                            ORDER BY ordinal_position
                            """
                        )
                        column_rows = connection.execute(
                            columns_sql,
                            {"schema_name": databricks_schema, "table_name": table_name},
                        ).mappings().all()
                        columns = [{"name": col["column_name"], "type": str(col["data_type"])} for col in column_rows]
                        primary_keys = {"constrained_columns": []}
                        foreign_keys = []
                        qualified_table_name = f"{databricks_catalog}.{databricks_schema}.{table_name}"
                    # Get table schema - for Oracle, specify schema if available
                    elif is_oracle and oracle_schema:
                        columns = inspector.get_columns(table_name, schema=oracle_schema.upper())
                        primary_keys = inspector.get_pk_constraint(table_name, schema=oracle_schema.upper())
                        foreign_keys_raw = inspector.get_foreign_keys(table_name, schema=oracle_schema.upper())
                        qualified_table_name = table_name
                    else:
                        columns = inspector.get_columns(table_name)
                        primary_keys = inspector.get_pk_constraint(table_name)
                        foreign_keys_raw = inspector.get_foreign_keys(table_name)
                        qualified_table_name = table_name

                    if not is_databricks:
                        # Process foreign keys safely
                        foreign_keys = []
                        for fk in foreign_keys_raw:
                            if fk.get("constrained_columns") and len(fk["constrained_columns"]) > 0:
                                foreign_keys.append({
                                    "column": fk["constrained_columns"][0],
                                    "references": fk.get("referred_table", "")
                                })

                    schema_info["tables"].append({
                        "name": qualified_table_name,
                        "catalog": databricks_catalog if is_databricks else None,
                        "schema": databricks_schema if is_databricks else (oracle_schema.upper() if is_oracle and oracle_schema else None),
                        "table": table_name,
                        "columns": columns if is_databricks else [{"name": col["name"], "type": str(col["type"])} for col in columns],
                        "primary_keys": primary_keys,
                        "foreign_keys": foreign_keys
                    })

                    logger.debug(f"Successfully extracted table {table_name} with {len(columns)} columns")

                    # thread-safe progress push
                    loop.call_soon_threadsafe(queue.put_nowait, {
                        "type": "progress",
                        "completedTables": idx,
                        "totalTables": total_tables,
                        "tableName": table_name,
                        "message": f"Extracting table {idx}/{total_tables}"
                    })
                except Exception as table_error:
                    error_msg = f"Error extracting table '{table_name}': {str(table_error)}"
                    logger.error(error_msg)
                    loop.call_soon_threadsafe(queue.put_nowait, {
                        "type": "warning",
                        "message": error_msg
                    })
                    # Still add the table with minimal info
                    schema_info["tables"].append({
                        "name": table_name,
                        "columns": [],
                        "primary_keys": {},
                        "foreign_keys": [],
                        "error": str(table_error)
                    })

            schema_info["min_date"] = min_date.isoformat()
            schema_info["max_date"] = max_date.isoformat()
            
            logger.info(f"Schema extraction completed successfully: {len(schema_info['tables'])} tables extracted")

    except Exception as e:
        error_msg = f"Error fetching schema information: {str(e)}"
        logger.error(error_msg, exc_info=True)
        loop.call_soon_threadsafe(queue.put_nowait, {
            "type": "error",
            "message": error_msg
        })
        schema_info["min_date"] = None
        schema_info["max_date"] = None
        # Don't raise - return empty schema so caller can handle it
    finally:
        if engine:
            try:
                engine.dispose()
                logger.info("Engine disposed")
            except Exception as e:
                logger.warning(f"Error disposing engine: {e}")

    return schema_info


# ---- Salesforce schema extraction (blocking; run in thread) ----
def get_salesforce_schema_structure(credentials: Dict[str, Any], queue, loop) -> Dict[str, Any]:
    """
    Extract schema structure from Salesforce using the describe() API.

    Maps Salesforce objects to tables and fields to columns.
    Uses OAuth2 session-based authentication only.

    Args:
        credentials: Dict with session_id (OAuth access_token) and instance_url
        queue: asyncio.Queue for progress updates
        loop: asyncio event loop for thread-safe queue puts

    Returns:
        Schema info dict with tables (Salesforce objects) and their fields
    """
    if not SALESFORCE_AVAILABLE:
        error_msg = "simple-salesforce is not installed. Cannot extract Salesforce schema."
        logger.error(error_msg)
        loop.call_soon_threadsafe(queue.put_nowait, {
            "type": "error",
            "message": error_msg
        })
        return {"tables": [], "min_date": None, "max_date": None}

    schema_info = {"tables": []}
    min_date = datetime.fromisoformat("2003-01-06")
    max_date = datetime.fromisoformat("2005-06-11")

    sf = None
    try:
        logger.info("Starting Salesforce schema extraction")

        # Create Salesforce client using OAuth2 (session_id + instance_url)
        instance_url = credentials.get("instance_url")
        session_id = credentials.get("session_id")

        if not session_id or not instance_url:
            raise ValueError("Salesforce requires session_id and instance_url for OAuth2 authentication")

        sf = Salesforce(instance_url=instance_url, session_id=session_id)

        logger.info("Salesforce client created successfully")

        # Get list of all accessible objects
        describe_result = sf.describe()
        sobjects = describe_result.get("sobjects", [])

        # Filter to queryable objects (skip non-queryable system objects)
        queryable_objects = [
            obj for obj in sobjects
            if obj.get("queryable", False) and not obj.get("name", "").endswith("__History")
        ]

        # Common standard objects to prioritize
        priority_objects = {
            "Account", "Contact", "Opportunity", "Lead", "Case",
            "Campaign", "Task", "Event", "User", "Product2",
            "Pricebook2", "PricebookEntry", "Order", "OrderItem",
            "Contract", "Quote", "Asset", "OpportunityLineItem"
        }

        # Sort: priority objects first, then custom objects, then others
        def sort_key(obj):
            name = obj.get("name", "")
            if name in priority_objects:
                return (0, name)
            elif name.endswith("__c"):  # Custom objects
                return (1, name)
            else:
                return (2, name)

        queryable_objects.sort(key=sort_key)

        # Limit to reasonable number for schema extraction
        MAX_OBJECTS = 100
        objects_to_process = queryable_objects[:MAX_OBJECTS]
        total_objects = len(objects_to_process)

        if total_objects == 0:
            error_msg = "No queryable Salesforce objects found"
            logger.error(error_msg)
            loop.call_soon_threadsafe(queue.put_nowait, {
                "type": "error",
                "message": error_msg
            })
            return {"tables": [], "min_date": None, "max_date": None}

        logger.info(f"Found {total_objects} queryable Salesforce objects")

        # Notify frontend of total objects
        loop.call_soon_threadsafe(queue.put_nowait, {
            "type": "started",
            "totalTables": total_objects,
            "message": f"Found {total_objects} Salesforce objects"
        })

        # Extract schema for each object
        for idx, obj in enumerate(objects_to_process, start=1):
            object_name = obj.get("name", "")

            try:
                logger.debug(f"Extracting object {idx}/{total_objects}: {object_name}")

                # Get detailed object description
                obj_describe = getattr(sf, object_name).describe()

                # Extract fields
                fields = obj_describe.get("fields", [])
                columns = []
                for field in fields:
                    field_name = field.get("name", "")
                    field_type = field.get("type", "string")
                    field_label = field.get("label", field_name)

                    # Map Salesforce types to SQL-like types for consistency
                    type_mapping = {
                        "id": "VARCHAR(18)",
                        "string": "VARCHAR(255)",
                        "picklist": "VARCHAR(255)",
                        "multipicklist": "TEXT",
                        "textarea": "TEXT",
                        "email": "VARCHAR(255)",
                        "phone": "VARCHAR(40)",
                        "url": "VARCHAR(255)",
                        "int": "INTEGER",
                        "double": "DOUBLE",
                        "currency": "DECIMAL(18,2)",
                        "percent": "DECIMAL(5,2)",
                        "boolean": "BOOLEAN",
                        "date": "DATE",
                        "datetime": "DATETIME",
                        "time": "TIME",
                        "reference": "VARCHAR(18)",
                        "base64": "BLOB",
                        "address": "TEXT",
                        "location": "TEXT",
                    }
                    mapped_type = type_mapping.get(field_type, "VARCHAR(255)")

                    columns.append({
                        "name": field_name,
                        "type": mapped_type,
                        "salesforce_type": field_type,
                        "label": field_label,
                    })

                # Extract relationships (foreign keys)
                foreign_keys = []
                for field in fields:
                    if field.get("type") == "reference":
                        ref_to = field.get("referenceTo", [])
                        if ref_to:
                            foreign_keys.append({
                                "column": field.get("name", ""),
                                "references": ref_to[0] if ref_to else "",
                                "relationship_name": field.get("relationshipName", ""),
                            })

                # Extract primary key (always Id for Salesforce)
                primary_keys = {
                    "constrained_columns": ["Id"],
                    "name": f"{object_name}_pk"
                }

                schema_info["tables"].append({
                    "name": object_name,
                    "columns": columns,
                    "primary_keys": primary_keys,
                    "foreign_keys": foreign_keys,
                    "label": obj.get("label", object_name),
                    "custom": obj.get("custom", False),
                })

                logger.debug(f"Extracted {object_name} with {len(columns)} fields")

                # Send progress update
                loop.call_soon_threadsafe(queue.put_nowait, {
                    "type": "progress",
                    "completedTables": idx,
                    "totalTables": total_objects,
                    "tableName": object_name,
                    "message": f"Extracting object {idx}/{total_objects}"
                })

            except Exception as obj_error:
                error_msg = f"Error extracting object '{object_name}': {str(obj_error)}"
                logger.error(error_msg)
                loop.call_soon_threadsafe(queue.put_nowait, {
                    "type": "warning",
                    "message": error_msg
                })
                # Add object with minimal info
                schema_info["tables"].append({
                    "name": object_name,
                    "columns": [],
                    "primary_keys": {},
                    "foreign_keys": [],
                    "error": str(obj_error)
                })

        schema_info["min_date"] = min_date.isoformat()
        schema_info["max_date"] = max_date.isoformat()

        logger.info(f"Salesforce schema extraction completed: {len(schema_info['tables'])} objects extracted")

    except SalesforceAuthenticationFailed as e:
        error_msg = f"Salesforce authentication failed: {str(e)}"
        logger.error(error_msg)
        loop.call_soon_threadsafe(queue.put_nowait, {
            "type": "error",
            "message": error_msg
        })
        schema_info["min_date"] = None
        schema_info["max_date"] = None

    except Exception as e:
        error_msg = f"Error fetching Salesforce schema: {str(e)}"
        logger.error(error_msg, exc_info=True)
        loop.call_soon_threadsafe(queue.put_nowait, {
            "type": "error",
            "message": error_msg
        })
        schema_info["min_date"] = None
        schema_info["max_date"] = None

    return schema_info
