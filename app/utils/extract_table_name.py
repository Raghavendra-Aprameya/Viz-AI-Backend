import logging
from sqlalchemy import create_engine, inspect
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

def extract_table_names(connection_string: str):
    """
    Extract all table names from a database using the provided connection string.

    Args:
        connection_string (str): SQLAlchemy database connection string

    Returns:
        list: List of table names in the database
    """
    engine = None
    try:
        # Create engine from connection string
        engine = create_engine(connection_string)

        # Create inspector to examine database schema
        inspector = inspect(engine)

        parsed_url = urlparse(connection_string)
        if parsed_url.scheme and "databricks" in parsed_url.scheme.lower():
            query_params = parse_qs(parsed_url.query or "")
            catalog_name = (query_params.get("catalog", [None])[0] or "").strip()
            schema_name = (query_params.get("schema", [None])[0] or "").strip()
            if catalog_name and schema_name:
                schema_ref = f"{catalog_name}.{schema_name}"
                table_names = inspector.get_table_names(schema=schema_ref)
                return table_names

        # Get all table names
        table_names = inspector.get_table_names()

        return table_names

    except Exception as e:
        logger.error(f"Error extracting table names: {e}", exc_info=True)
        return []
    finally:
        # Dispose engine to prevent connection leaks
        if engine is not None:
            engine.dispose()
    
