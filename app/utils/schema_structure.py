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

def get_schema_structure(connection_string: str, queue, loop):
    """
    Blocking schema extraction that runs in a thread.
    Uses loop.call_soon_threadsafe(queue.put_nowait, msg) to push progress back to the async queue.
    """
    engine = create_engine(connection_string)
    inspector = inspect(engine)
    schema_info = {"tables": []}

    min_date = datetime.fromisoformat("2003-01-06")
    max_date = datetime.fromisoformat("2005-06-11")

    try:
        with engine.connect() as connection:
            table_names = inspector.get_table_names()
            total_tables = len(table_names)

            # send an initial snapshot if you want
            loop.call_soon_threadsafe(queue.put_nowait, {
                "type": "started",
                "totalTables": total_tables,
                "message": f"Found {total_tables} tables"
            })

            for idx, table_name in enumerate(table_names, start=1):
                # Blocking inspector calls (these will execute in the thread)
                columns = inspector.get_columns(table_name)
                primary_keys = inspector.get_pk_constraint(table_name)
                foreign_keys = [
                    {"column": fk["constrained_columns"][0], "references": fk["referred_table"]}
                    for fk in inspector.get_foreign_keys(table_name)
                ]

                schema_info["tables"].append({
                    "name": table_name,
                    "columns": [{"name": col["name"], "type": str(col["type"])} for col in columns],
                    "primary_keys": primary_keys,
                    "foreign_keys": foreign_keys
                })

                # thread-safely push a progress update into the asyncio.Queue
                loop.call_soon_threadsafe(queue.put_nowait, {
                    "type": "progress",
                    "completedTables": idx,
                    "totalTables": total_tables,
                    "tableName": table_name,
                    "message": f"Extracting table {idx}/{total_tables}"
                })

            schema_info["min_date"] = min_date.isoformat()
            schema_info["max_date"] = max_date.isoformat()

    except Exception as e:
        # push error to queue and return partial schema_info
        loop.call_soon_threadsafe(queue.put_nowait, {
            "type": "error",
            "message": f"Error fetching schema information: {e}"
        })
        schema_info["min_date"] = None
        schema_info["max_date"] = None

    return schema_info
