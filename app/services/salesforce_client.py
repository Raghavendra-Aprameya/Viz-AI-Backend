"""
Salesforce Client Manager

Manages Salesforce connections using simple-salesforce library with:
- LRU caching per connection ID to prevent client recreation
- Support for both username/password/token and OAuth2 authentication
- Thread-safe access for async/concurrent operations
- Automatic cleanup on connection updates/deletes

This module provides a singleton manager for Salesforce REST API clients,
similar to ExternalEngineManager but for Salesforce instead of SQLAlchemy.
"""

import logging
import threading
from collections import OrderedDict
from typing import Optional, Dict, Tuple, Any
from uuid import UUID
from datetime import datetime

try:
    from simple_salesforce import Salesforce
    from simple_salesforce.exceptions import SalesforceAuthenticationFailed
except ImportError:
    raise ImportError(
        "simple-salesforce is required for Salesforce integration. "
        "Install it with: pip install simple-salesforce"
    )

logger = logging.getLogger(__name__)

# Default cache size for Salesforce clients
SALESFORCE_CLIENT_CACHE_SIZE = 50


class SalesforceClientManager:
    """
    Manages Salesforce REST API clients for database connections.

    Features:
    - LRU caching per connection ID (prevents client recreation)
    - Automatic client reuse across requests
    - Thread-safe for concurrent access
    - Invalidation on connection updates/deletes
    - Support for both authentication methods:
        1. Username + Password + Security Token
        2. OAuth2 (session_id + instance_url)

    Usage:
        manager = SalesforceClientManager()
        sf = manager.get_client(
            connection_id=UUID("..."),
            username="user@example.com",
            password="password",
            security_token="token"
        )
        # Use sf for SOQL queries...
        # No need to disconnect - manager handles lifecycle
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

    def __init__(self, max_cache_size: int = SALESFORCE_CLIENT_CACHE_SIZE):
        """
        Initialize the Salesforce client manager.

        Args:
            max_cache_size: Maximum number of clients to cache (default: 50)
        """
        # Only initialize once (singleton pattern)
        if hasattr(self, '_initialized'):
            return

        # Cache structure: connection_id -> (credentials_hash, Salesforce client)
        self._clients: OrderedDict[UUID, Tuple[str, Salesforce]] = OrderedDict()
        self._max_cache_size = max_cache_size
        self._instance_lock = threading.Lock()
        self._initialized = True
        logger.info(f"SalesforceClientManager initialized with cache size {max_cache_size}")

    def _create_credentials_hash(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        security_token: Optional[str] = None,
        instance_url: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Create a hash string from credentials for cache comparison"""
        if session_id and instance_url:
            return f"oauth:{instance_url}:{session_id[:20]}"
        return f"basic:{username}:{password}:{security_token}"
    def refresh_client(self, connection_id: UUID, **kwargs) -> Salesforce:
        """Forcefully remove old client and create a new one"""
        self.invalidate_client(connection_id)
        return self.get_client(connection_id=connection_id, **kwargs)
    def get_client(
        self,
        connection_id: UUID,
        username: Optional[str] = None,
        password: Optional[str] = None,
        security_token: Optional[str] = None,
        instance_url: Optional[str] = None,
        session_id: Optional[str] = None,
        domain: str = "login",
    ) -> Salesforce:
        """
        Get or create a cached Salesforce client for a connection.

        Supports two authentication methods:
        1. Username + Password + Security Token (basic auth)
        2. Session ID + Instance URL (OAuth2)

        Args:
            connection_id: UUID of the DatabaseConnectionModel
            username: Salesforce username (for basic auth)
            password: Salesforce password (for basic auth)
            security_token: Salesforce security token (for basic auth)
            instance_url: Salesforce instance URL (for OAuth2)
            session_id: OAuth2 access token (for OAuth2)
            domain: Salesforce domain ('login' for production, 'test' for sandbox)

        Returns:
            Salesforce client instance (cached or newly created)

        Raises:
            SalesforceAuthenticationFailed: If authentication fails
            ValueError: If required credentials are missing
        """
        credentials_hash = self._create_credentials_hash(
            username, password, security_token, instance_url, session_id
        )

        with self._instance_lock:
            # Check if client exists and credentials haven't changed
            if connection_id in self._clients:
                cached_hash, cached_client = self._clients[connection_id]

                if cached_hash == credentials_hash:
                    # Move to end (LRU: most recently used)
                    self._clients.move_to_end(connection_id)
                    logger.debug(f"Reusing cached Salesforce client for connection {connection_id}")
                    return cached_client
                else:
                    # Credentials changed, remove old client
                    logger.info(f"Credentials changed for {connection_id}, creating new client")
                    del self._clients[connection_id]

            # Evict oldest client if cache is full
            if len(self._clients) >= self._max_cache_size:
                self._evict_oldest()

            # Create new client
            client = self._create_client(
                username, password, security_token, instance_url, session_id, domain
            )
            self._clients[connection_id] = (credentials_hash, client)
            logger.info(
                f"Created new Salesforce client for connection {connection_id} "
                f"(cache_size={len(self._clients)}/{self._max_cache_size})"
            )

            return client

    def _create_client(
        self,
        username: Optional[str],
        password: Optional[str],
        security_token: Optional[str],
        instance_url: Optional[str],
        session_id: Optional[str],
        domain: str,
    ) -> Salesforce:
        """
        Create a new Salesforce client.

        Args:
            username: Salesforce username (for basic auth)
            password: Salesforce password (for basic auth)
            security_token: Salesforce security token (for basic auth)
            instance_url: Salesforce instance URL (for OAuth2)
            session_id: OAuth2 access token (for OAuth2)
            domain: Salesforce domain

        Returns:
            Salesforce client instance

        Raises:
            ValueError: If required credentials are missing
            SalesforceAuthenticationFailed: If authentication fails
        """
        # OAuth2 authentication (session_id + instance_url)
        if session_id and instance_url:
            logger.debug(f"Creating Salesforce client with OAuth2 at {instance_url}")
            return Salesforce(
                instance_url=instance_url,
                session_id=session_id,
            )

        # Username/password/token authentication
        if username and password:
            logger.debug(f"Creating Salesforce client with username/password for {username}")
            return Salesforce(
                username=username,
                password=password,
                security_token=security_token or "",
                domain=domain,
            )

        raise ValueError(
            "Invalid Salesforce credentials. Provide either "
            "(username, password, security_token) or (session_id, instance_url)"
        )

    def _evict_oldest(self):
        """Evict the least recently used client from cache."""
        if self._clients:
            conn_id, (_, client) = self._clients.popitem(last=False)
            logger.info(f"Evicted Salesforce client for connection {conn_id} (LRU, cache was full)")

    def invalidate_client(self, connection_id: UUID):
        """
        Invalidate and remove client for a connection.

        This should be called when:
        - Connection is updated (credentials changed)
        - Connection is deleted

        Args:
            connection_id: UUID of the connection to invalidate
        """
        with self._instance_lock:
            if connection_id in self._clients:
                del self._clients[connection_id]
                logger.info(f"Invalidated Salesforce client for connection {connection_id}")
            else:
                logger.debug(
                    f"Invalidate requested for {connection_id}, but not in cache"
                )

    def dispose_all(self):
        """
        Dispose all cached clients.

        This should be called on application shutdown.
        """
        with self._instance_lock:
            client_count = len(self._clients)
            logger.info(f"Disposing all {client_count} cached Salesforce clients")
            self._clients.clear()
            logger.info("All Salesforce clients disposed")

    def test_connection(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        security_token: Optional[str] = None,
        instance_url: Optional[str] = None,
        session_id: Optional[str] = None,
        domain: str = "login",
    ) -> Dict[str, Any]:
        """
        Test Salesforce connection credentials without caching.

        Args:
            username: Salesforce username (for basic auth)
            password: Salesforce password (for basic auth)
            security_token: Salesforce security token (for basic auth)
            instance_url: Salesforce instance URL (for OAuth2)
            session_id: OAuth2 access token (for OAuth2)
            domain: Salesforce domain

        Returns:
            Dict with 'success' boolean and 'message' or 'error' string
        """
        try:
            client = self._create_client(
                username, password, security_token, instance_url, session_id, domain
            )
            # Test the connection by querying the organization info
            org_info = client.query("SELECT Id, Name FROM Organization LIMIT 1")
            org_name = org_info.get("records", [{}])[0].get("Name", "Unknown")
            return {
                "success": True,
                "message": f"Successfully connected to Salesforce org: {org_name}",
                "org_name": org_name,
            }
        except SalesforceAuthenticationFailed as e:
            logger.error(f"Salesforce authentication failed: {e}")
            return {
                "success": False,
                "error": f"Authentication failed: {str(e)}",
            }
        except Exception as e:
            logger.error(f"Salesforce connection test failed: {e}")
            return {
                "success": False,
                "error": f"Connection failed: {str(e)}",
            }

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the client cache.

        Returns:
            Dictionary with cache statistics
        """
        with self._instance_lock:
            cached_count = len(self._clients)
            return {
                "cached_clients": cached_count,
                "max_cache_size": self._max_cache_size,
                "cache_utilization": f"{cached_count / self._max_cache_size * 100:.1f}%",
                "connection_ids": [str(conn_id) for conn_id in self._clients.keys()],
            }


# Singleton instance
salesforce_client_manager = SalesforceClientManager()
