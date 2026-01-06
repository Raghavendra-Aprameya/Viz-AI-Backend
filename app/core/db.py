"""
This module initializes the SQLAlchemy engine, creates database tables from ORM models,
and provides a generator function for dependency injection of database sessions.

Features:
- Configures SQLAlchemy engine with connection pooling options.
- Automatically creates tables defined in ORM models.
- Provides `get_db` generator for use in FastAPI or other frameworks.
"""

from typing import Generator
import logging

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from app.core.settings import settings
from app.core.base import Base
from app.utils.constants import POOL_SIZE, MAX_OVERFLOW, POOL_RECYCLE, POOL_TIMEOUT

logger = logging.getLogger(__name__)


engine = create_engine(
    url=settings.DB_URI,
    pool_pre_ping=True,
    pool_recycle=POOL_RECYCLE,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_timeout=POOL_TIMEOUT,
    connect_args={
        "connect_timeout": 10,  # Fail fast if DB is unreachable
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    },
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False,)
# Base.metadata.create_all(engine)
# inspector = inspect(engine)
# print(f"Tables in database after creation: {inspector.get_table_names()}")


def get_db() -> Generator:
    """Create the database tables"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_pool_status() -> dict:
    """Get current connection pool status for monitoring"""
    pool = engine.pool
    return {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "max_overflow": MAX_OVERFLOW,
        "pool_size": POOL_SIZE,
    }


def log_pool_status():
    """Log current pool status for debugging connection issues"""
    try:
        status = get_pool_status()
        logger.info(
            f"Pool status - Size: {status['size']}, "
            f"Checked in: {status['checked_in']}, "
            f"Checked out: {status['checked_out']}, "
            f"Overflow: {status['overflow']}/{status['max_overflow']}"
        )
        if status['checked_out'] >= POOL_SIZE + MAX_OVERFLOW - 5:
            logger.warning("Connection pool nearly exhausted! Check for connection leaks.")
    except Exception as e:
        logger.error(f"Error getting pool status: {e}")

# External Database Engine Manager
# Singleton instance for managing external user database connections
from app.core.external_engine_manager import ExternalEngineManager

external_engine_manager = ExternalEngineManager()
