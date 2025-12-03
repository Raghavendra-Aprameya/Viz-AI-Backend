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
from typing import Optional, Union, Dict
import json
from urllib.parse import quote_plus

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


if __name__ == "__main__":
    import asyncio
    import threading
    
    # Convert JDBC connection string to SQLAlchemy format
    # JDBC: jdbc:oracle:thin:@170.187.237.181:1521/ORCLPDB1
    # SQLAlchemy: oracle+cx_oracle://username:password@host:port/service_name
    username = "devuser"
    password = "DevPass#2025"
    host = "170.187.237.181"
    port = "1521"
    service_name = "ORCLPDB1"
    
    connection_string = f"oracle+cx_oracle://{username}:{password}@{host}:{port}/{service_name}"
    
    print(f"Testing schema extraction with connection: {host}:{port}/{service_name}")
    print("-" * 60)
    
    # Create event loop and queue
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    queue = asyncio.Queue()
    
    # Result storage
    result = {"schema_info": None, "error": None}
    
    def run_in_thread():
        """Run the blocking function in a thread"""
        try:
            schema_info = get_schema_structure(connection_string, queue, loop)
            result["schema_info"] = schema_info
        except Exception as e:
            result["error"] = str(e)
        finally:
            # Signal completion
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "complete"})
    
    # Start the blocking function in a thread
    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()
    
    # Monitor queue for progress updates
    async def monitor_progress():
        while True:
            try:
                # Wait for message with timeout
                message = await asyncio.wait_for(queue.get(), timeout=1.0)
                
                if message["type"] == "started":
                    print(f"✓ {message['message']}")
                    print(f"  Total tables to process: {message['totalTables']}")
                
                elif message["type"] == "progress":
                    print(f"  [{message['completedTables']}/{message['totalTables']}] Processing: {message['tableName']}")
                
                elif message["type"] == "error":
                    print(f"✗ ERROR: {message['message']}")
                    result["error"] = message["message"]
                    break
                
                elif message["type"] == "complete":
                    break
                    
            except asyncio.TimeoutError:
                # Check if thread is still alive
                if not thread.is_alive():
                    break
                continue
    
    # Run the monitoring
    try:
        loop.run_until_complete(monitor_progress())
    except KeyboardInterrupt:
        print("\n⚠ Interrupted by user")
    finally:
        loop.close()
    
    # Wait for thread to complete
    thread.join(timeout=30)
    
    # Print results
    print("\n" + "=" * 60)
    if result["error"]:
        print(f"✗ Test failed with error: {result['error']}")
    elif result["schema_info"]:
        schema_info = result["schema_info"]
        print(f"✓ Schema extraction completed successfully!")
        print(f"\nSummary:")
        print(f"  - Total tables: {len(schema_info.get('tables', []))}")
        print(f"  - Min date: {schema_info.get('min_date')}")
        print(f"  - Max date: {schema_info.get('max_date')}")
        
        # Show first few tables as sample
        tables = schema_info.get("tables", [])
        if tables:
            print(f"\nSample tables (first 5):")
            for table in tables[:5]:
                print(f"  - {table['name']}: {len(table['columns'])} columns")
                if table.get('primary_keys', {}).get('constrained_columns'):
                    print(f"    PK: {', '.join(table['primary_keys']['constrained_columns'])}")
                if table.get('foreign_keys'):
                    print(f"    FK: {len(table['foreign_keys'])} foreign key(s)")
        
        # Optionally print full JSON (commented out to avoid clutter)
        # print("\nFull schema info:")
        # print(json.dumps(schema_info, indent=2, default=str))
    else:
        print("✗ Test completed but no result was returned")