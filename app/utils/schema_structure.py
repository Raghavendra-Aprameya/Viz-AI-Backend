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
from sqlalchemy import create_engine, inspect
from datetime import datetime
from typing import Optional
import json
import logging
from urllib.parse import urlparse

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
        oracle_schema = parsed_url.username if is_oracle else None
        
        logger.info(f"Starting schema extraction - DB Type: {'Oracle' if is_oracle else 'Other'}, Schema: {oracle_schema}")
        
        engine = create_engine(connection_string, pool_pre_ping=True)
        inspector = inspect(engine)
        
        logger.info("Engine created successfully, connecting to database...")

        with engine.connect() as connection:
            logger.info("Database connection established")
            
            # For Oracle, try with schema first
            if is_oracle and oracle_schema:
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
                    
                    # Get table schema - for Oracle, specify schema if available
                    if is_oracle and oracle_schema:
                        columns = inspector.get_columns(table_name, schema=oracle_schema.upper())
                        primary_keys = inspector.get_pk_constraint(table_name, schema=oracle_schema.upper())
                        foreign_keys_raw = inspector.get_foreign_keys(table_name, schema=oracle_schema.upper())
                    else:
                        columns = inspector.get_columns(table_name)
                        primary_keys = inspector.get_pk_constraint(table_name)
                        foreign_keys_raw = inspector.get_foreign_keys(table_name)

                    # Process foreign keys safely
                    foreign_keys = []
                    for fk in foreign_keys_raw:
                        if fk.get("constrained_columns") and len(fk["constrained_columns"]) > 0:
                            foreign_keys.append({
                                "column": fk["constrained_columns"][0],
                                "references": fk.get("referred_table", "")
                            })

                    schema_info["tables"].append({
                        "name": table_name,
                        "columns": [{"name": col["name"], "type": str(col["type"])} for col in columns],
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