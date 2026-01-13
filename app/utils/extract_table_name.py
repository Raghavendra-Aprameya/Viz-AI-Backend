import logging
from sqlalchemy import create_engine, inspect

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
    
