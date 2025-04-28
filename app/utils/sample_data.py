import json
from sqlalchemy import create_engine, inspect
from typing import Dict, List

def get_sample_data(connection_string: str) -> str:
    """
    Fetches 10 rows of sample data from each table in the database along with column names.
    Returns the sample data as a JSON string.
    """
    engine = create_engine(connection_string)
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
        print(f"Error fetching sample data: {e}")
        raise
