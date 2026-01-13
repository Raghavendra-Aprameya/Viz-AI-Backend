"""
External Database Engine Manager

Manages SQLAlchemy engines for external user database connections with:
- LRU caching per connection ID to prevent engine recreation
- Connection pooling with reasonable limits
- Thread-safe access for async/concurrent operations
- Automatic cleanup on connection updates/deletes
- Graceful degradation if pooling fails

This module addresses memory leaks caused by creating new engines
for each query execution to external databases.
"""

import logging
import threading
from collections import OrderedDict
from typing import Optional, Dict, Tuple
from uuid import UUID
from contextlib import contextmanager

from sqlalchemy import create_engine, Engine
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import SQLAlchemyError

from app.utils.constants import (
    EXTERNAL_POOL_SIZE,
    EXTERNAL_MAX_OVERFLOW,
    EXTERNAL_POOL_RECYCLE,
    EXTERNAL_CONNECT_TIMEOUT,
    EXTERNAL_ENGINE_CACHE_SIZE,
    ORACLE_POOL_SIZE,
    ORACLE_MAX_OVERFLOW,
)

logger = logging.getLogger(__name__)


class ExternalEngineManager:
    """
    Manages SQLAlchemy engines for external database connections.

    Features:
    - LRU caching per connection ID (prevents engine recreation)
    - Automatic engine reuse across requests
    - Thread-safe for concurrent access
    - Invalidation on connection updates/deletes
    - Graceful shutdown with dispose_all()
    - Database-specific pool configurations

    Usage:
        manager = ExternalEngineManager()
        engine = manager.get_engine(
            connection_id=UUID("..."),
            connection_string="postgresql://...",
            db_type="postgres"
        )
        # Use engine...
        # No need to dispose - manager handles lifecycle
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Thread-safe singleton pattern"""
        if cls._instance is None:
            with cls._lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_cache_size: int = EXTERNAL_ENGINE_CACHE_SIZE):
        """
        Initialize the engine manager.

        Args:
            max_cache_size: Maximum number of engines to cache (default: 100)
        """
        # Only initialize once (singleton pattern)
        if hasattr(self, '_initialized'):
            return

        self._engines: OrderedDict[UUID, Tuple[str, Engine]] = OrderedDict()
        self._max_cache_size = max_cache_size
        self._instance_lock = threading.Lock()
        self._initialized = True
        logger.info(f"ExternalEngineManager initialized with cache size {max_cache_size}")

    def get_engine(
        self,
        connection_id: UUID,
        connection_string: str,
        db_type: Optional[str] = None
    ) -> Engine:
        """
        Get or create a cached engine for a database connection.

        Args:
            connection_id: UUID of the DatabaseConnectionModel
            connection_string: Decrypted database connection string
            db_type: Database type ('postgres', 'mysql', 'oracle', 'spreadsheet')

        Returns:
            SQLAlchemy Engine instance (cached or newly created)

        Thread Safety:
            This method is thread-safe and can be called concurrently.
            The engine itself is also thread-safe once returned.
        """
        with self._instance_lock:
            # Check if engine exists and connection string hasn't changed
            if connection_id in self._engines:
                cached_conn_str, cached_engine = self._engines[connection_id]

                if cached_conn_str == connection_string:
                    # Move to end (LRU: most recently used)
                    self._engines.move_to_end(connection_id)
                    logger.debug(f"Reusing cached engine for connection {connection_id}")
                    return cached_engine
                else:
                    # Connection string changed, invalidate old engine
                    logger.info(f"Connection string changed for {connection_id}, disposing old engine")
                    try:
                        cached_engine.dispose()
                    except Exception as e:
                        logger.error(f"Error disposing old engine for {connection_id}: {e}")
                    del self._engines[connection_id]

            # Evict oldest engine if cache is full
            if len(self._engines) >= self._max_cache_size:
                self._evict_oldest()

            # Create new engine
            engine = self._create_engine(connection_string, db_type)
            self._engines[connection_id] = (connection_string, engine)
            logger.info(
                f"Created new engine for connection {connection_id} "
                f"(db_type={db_type}, cache_size={len(self._engines)}/{self._max_cache_size})"
            )

            return engine

    def _create_engine(self, connection_string: str, db_type: Optional[str]) -> Engine:
        """
        Create a new SQLAlchemy engine with appropriate pool settings.

        Args:
            connection_string: Database connection string
            db_type: Database type for pool configuration

        Returns:
            SQLAlchemy Engine instance

        Raises:
            Falls back to NullPool if engine creation with pooling fails
        """
        try:
            pool_config = self._get_pool_config(db_type)

            # Add connect timeout to connect_args (database-specific)
            connect_args = pool_config.pop('connect_args', {})

            # Oracle doesn't support connect_timeout in the same way
            if db_type not in ("oracledb", "oracle"):
                connect_args['connect_timeout'] = EXTERNAL_CONNECT_TIMEOUT

            engine = create_engine(
                connection_string,
                connect_args=connect_args,
                **pool_config
            )

            pool_size = pool_config.get('pool_size', 'N/A')
            logger.debug(
                f"Created engine with pool_size={pool_size}, db_type={db_type}"
            )
            return engine

        except SQLAlchemyError as e:
            logger.error(f"Failed to create engine with pooling: {e}")
            # Fallback to NullPool (no connection pooling)
            logger.warning("Falling back to NullPool (no connection pooling)")

            # Try without connect_timeout for Oracle, with it for others
            fallback_connect_args = {}
            if db_type not in ("oracledb", "oracle"):
                fallback_connect_args['connect_timeout'] = EXTERNAL_CONNECT_TIMEOUT

            return create_engine(
                connection_string,
                poolclass=NullPool,
                connect_args=fallback_connect_args
            )

    def _get_pool_config(self, db_type: Optional[str]) -> dict:
        """
        Get pool configuration based on database type.

        Args:
            db_type: Database type ('postgres', 'mysql', 'oracle', 'spreadsheet')

        Returns:
            Dictionary of pool configuration parameters
        """
        if db_type == "oracledb" or db_type == "oracle":
            # Oracle has stricter licensing - use smaller pool
            return {
                "pool_size": ORACLE_POOL_SIZE,
                "max_overflow": ORACLE_MAX_OVERFLOW,
                "pool_pre_ping": True,
                "pool_recycle": EXTERNAL_POOL_RECYCLE,
            }
        elif db_type == "spreadsheet":
            # Google Sheets or similar - no pooling needed
            return {"poolclass": NullPool}
        else:
            # PostgreSQL, MySQL, or default
            return {
                "pool_size": EXTERNAL_POOL_SIZE,
                "max_overflow": EXTERNAL_MAX_OVERFLOW,
                "pool_pre_ping": True,
                "pool_recycle": EXTERNAL_POOL_RECYCLE,
            }

    def _evict_oldest(self):
        """
        Evict the least recently used engine from cache.

        Called when cache is full and a new engine needs to be added.
        """
        if self._engines:
            conn_id, (conn_str, engine) = self._engines.popitem(last=False)
            try:
                engine.dispose()
                logger.info(
                    f"Evicted engine for connection {conn_id} (LRU, cache was full)"
                )
            except Exception as e:
                logger.error(f"Error disposing evicted engine for {conn_id}: {e}")

    def invalidate_engine(self, connection_id: UUID):
        """
        Invalidate and dispose engine for a connection.

        This should be called when:
        - Connection is updated (connection string changed)
        - Connection is deleted

        Args:
            connection_id: UUID of the connection to invalidate
        """
        with self._instance_lock:
            if connection_id in self._engines:
                conn_str, engine = self._engines[connection_id]
                try:
                    engine.dispose()
                    logger.info(f"Disposed engine for connection {connection_id}")
                except Exception as e:
                    logger.error(f"Error disposing engine for {connection_id}: {e}")
                finally:
                    del self._engines[connection_id]
            else:
                logger.debug(
                    f"Invalidate requested for {connection_id}, but not in cache"
                )

    def dispose_all(self):
        """
        Dispose all cached engines.

        This should be called on application shutdown to ensure
        all database connections are properly closed.

        Thread Safety:
            This method acquires the instance lock, so it's safe to call
            during shutdown even if other threads might be accessing engines.
        """
        with self._instance_lock:
            engine_count = len(self._engines)
            logger.info(f"Disposing all {engine_count} cached engines")

            for conn_id, (conn_str, engine) in list(self._engines.items()):
                try:
                    engine.dispose()
                    logger.debug(f"Disposed engine for connection {conn_id}")
                except Exception as e:
                    logger.error(f"Error disposing engine for {conn_id}: {e}")

            self._engines.clear()
            logger.info("All engines disposed")

    @contextmanager
    def get_connection(
        self,
        connection_id: UUID,
        connection_string: str,
        db_type: Optional[str] = None
    ):
        """
        Context manager for getting a database connection.

        Usage:
            with manager.get_connection(conn_id, conn_str) as conn:
                result = conn.execute(text("SELECT * FROM table"))

        Args:
            connection_id: UUID of the database connection
            connection_string: Decrypted connection string
            db_type: Database type

        Yields:
            SQLAlchemy Connection instance
        """
        engine = self.get_engine(connection_id, connection_string, db_type)
        connection = engine.connect()
        try:
            yield connection
        finally:
            connection.close()

    def get_cache_stats(self) -> Dict:
        """
        Get statistics about the engine cache.

        Returns:
            Dictionary with cache statistics:
            - cached_engines: Number of engines currently cached
            - max_cache_size: Maximum cache size
            - cache_utilization: Percentage of cache used
            - connection_ids: List of cached connection IDs (for debugging)
        """
        with self._instance_lock:
            cached_count = len(self._engines)
            return {
                "cached_engines": cached_count,
                "max_cache_size": self._max_cache_size,
                "cache_utilization": f"{cached_count / self._max_cache_size * 100:.1f}%",
                "connection_ids": [str(conn_id) for conn_id in self._engines.keys()]
            }
