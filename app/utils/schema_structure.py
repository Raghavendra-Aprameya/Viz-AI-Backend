from sqlalchemy import create_engine, inspect

from datetime import datetime, timedelta
from app.utils.crypt import decrypt_string

def get_schema_structure(connection_string: str, db_type: str):
    engine = create_engine(connection_string)
    inspector = inspect(engine)

    schema_info = {"tables": []}
    # max_date = datetime.now().date()
    # min_date = max_date - timedelta(days=183) 
    min_date= datetime.fromisoformat("2003-01-06")
    max_date= datetime.fromisoformat("2005-06-11")

    try:
        with engine.connect() as connection:
            for table_name in inspector.get_table_names():
                columns = inspector.get_columns(table_name)
                primary_keys = inspector.get_pk_constraint(table_name)
                foreign_keys = [
                    {"column": fk["constrained_columns"][0], "references": fk["referred_table"]}
                    for fk in inspector.get_foreign_keys(table_name)
                ]

                schema_info["tables"].append({
                    "name": table_name,
                    "columns": [
                        {"name": col["name"], "type": str(col["type"])}
                        for col in columns
                    ],
                    "primary_keys": primary_keys,
                    "foreign_keys": foreign_keys
                })

        schema_info["min_date"] = min_date.isoformat()
        schema_info["max_date"] = max_date.isoformat()
        print(f"Database Date Range: Min Date: {min_date}, Max Date: {max_date}")

    except Exception as e:
        print(f"Error fetching schema information: {e}. Returning schema info with default date range.")
        schema_info["min_date"] = None
        schema_info["max_date"] = None

    return schema_info