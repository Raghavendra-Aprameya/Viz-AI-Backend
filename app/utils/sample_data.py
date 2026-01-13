import json
import logging
from sqlalchemy import create_engine, inspect
from typing import Dict, List

logger = logging.getLogger(__name__)

def get_sample_data(connection_string: str, db_type: str = None) -> str:
    """
    Fetches 10 rows of sample data from each table in the database along with column names.
    Returns the sample data as a JSON string.

    Uses production-safe engine configuration to prevent stale connections.
    """
    # Use production-safe configuration for external databases
    connect_args = {}
    if db_type in ("postgres", "postgresql"):
        connect_args = {
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        }
    elif db_type not in ("oracledb", "oracle"):
        connect_args = {"connect_timeout": 10}
    
    engine = create_engine(
        connection_string,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args=connect_args,
    )
    inspector = inspect(engine)
    sample_data = {}

    try:
        with engine.connect() as connection:
            for table_name in inspector.get_table_names():
                columns = inspector.get_columns(table_name)
                column_names = [col["name"] for col in columns]

                query = f"SELECT {', '.join(column_names)} FROM {table_name} LIMIT 10"
                result = connection.execute(query).fetchall()

                rows = [dict(zip(column_names, row)) for row in result]

                sample_data[table_name] = {
                    "columns": column_names,
                    "rows": rows
                }

        sample_data_str = json.dumps(sample_data, indent=2)
        return sample_data_str

    except Exception as e:
        logger.error(f"Error fetching sample data: {e}", exc_info=True)
        raise
    finally:
        # Dispose engine to prevent connection leaks
        engine.dispose()
