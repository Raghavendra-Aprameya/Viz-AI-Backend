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
from sqlalchemy import create_engine, inspect
from datetime import datetime
from typing import Optional
import asyncio

def get_schema_structure(connection_string: str, task_queue: Optional[asyncio.Queue] = None):
    engine = create_engine(connection_string)
    inspector = inspect(engine)
    schema_info = {"tables": []}

    min_date = datetime.fromisoformat("2003-01-06")
    max_date = datetime.fromisoformat("2005-06-11")

    try:
        with engine.connect() as connection:
            table_names = inspector.get_table_names()
            total_tables = len(table_names)

            for idx, table_name in enumerate(table_names, start=1):
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

                # Push progress to queue if available
                if task_queue:
                    # Use asyncio.create_task only in async context; here we are in sync, so use `asyncio.get_event_loop().create_task`
                    loop = asyncio.get_event_loop()
                    loop.create_task(
                        task_queue.put({
                            "type": "progress",
                            "completedTables": idx,
                            "totalTables": total_tables,
                            "tableName": table_name,
                            "message": f"Extracting table {idx}/{total_tables}"
                        })
                    )

        schema_info["min_date"] = min_date.isoformat()
        schema_info["max_date"] = max_date.isoformat()

    except Exception as e:
        print(f"Error fetching schema information: {e}. Returning partial schema info.")
        schema_info["min_date"] = None
        schema_info["max_date"] = None

    return schema_info
