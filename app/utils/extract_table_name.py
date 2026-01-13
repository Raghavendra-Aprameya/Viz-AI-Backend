import logging
from sqlalchemy import create_engine, inspect

logger = logging.getLogger(__name__)

def extract_table_names(connection_string: str, db_type: str = None):
    """
    Extract all table names from a database using the provided connection string.

    Uses production-safe engine configuration to prevent stale connections.

    Args:
        connection_string (str): SQLAlchemy database connection string
        db_type (str, optional): Database type ('postgres', 'mysql', 'oracle', etc.)

    Returns:
        list: List of table names in the database
    """
    engine = None
    try:
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
        
        # Create engine with production-safe configuration
        engine = create_engine(
            connection_string,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args=connect_args,
        )

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
    
