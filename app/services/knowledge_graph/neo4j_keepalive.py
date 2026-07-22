"""Background AuraDB ping so free-tier instances stay awake."""

from __future__ import annotations

import asyncio
import logging
import os

from app.services.knowledge_graph.neo4j_client import is_configured, verify_connectivity

logger = logging.getLogger(__name__)

_task: asyncio.Task | None = None


def _interval_seconds() -> int:
    return int(os.getenv("NEO4J_KEEPALIVE_SECONDS", "300"))


async def _loop() -> None:
    while True:
        try:
            await verify_connectivity()
            logger.info("Neo4j AuraDB keepalive OK")
        except Exception as exc:
            logger.warning("Neo4j AuraDB keepalive failed: %s", exc)
        await asyncio.sleep(_interval_seconds())


def start() -> None:
    """Start the keepalive task if Neo4j is configured. No-op otherwise."""
    global _task
    if _task is not None or not is_configured():
        return
    _task = asyncio.create_task(_loop(), name="neo4j-keepalive")
    logger.info("Neo4j AuraDB keepalive started (every %ss)", _interval_seconds())


async def stop() -> None:
    """Cancel the keepalive task on shutdown."""
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None
    logger.info("Neo4j AuraDB keepalive stopped")
