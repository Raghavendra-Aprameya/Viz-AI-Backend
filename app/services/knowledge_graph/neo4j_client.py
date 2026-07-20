"""Fail-closed Neo4j AuraDB persistence for cumulative per-user graphs.

Upload/delete APIs succeed only when both Postgres and AuraDB complete.
Entities are shared across one user's documents; every node/relationship
retains document provenance.
"""

from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

logger = logging.getLogger(__name__)

_driver: AsyncDriver | None = None
_schema_ready = False


def _username() -> str:
    # Aura connection panels expose NEO4J_USERNAME; keep NEO4J_USER as fallback.
    return (
        os.getenv("NEO4J_USERNAME")
        or os.getenv("NEO4J_USER")
        or "neo4j"
    ).strip()


def is_configured() -> bool:
    """Return whether all required AuraDB connection values are present."""
    return all((os.getenv("NEO4J_URI"), os.getenv("NEO4J_PASSWORD")))


def _database() -> str:
    return (os.getenv("NEO4J_DATABASE", "neo4j") or "neo4j").strip()


def _get_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        uri = os.getenv("NEO4J_URI")
        password = os.getenv("NEO4J_PASSWORD")
        if not uri or not password:
            raise RuntimeError("Neo4j AuraDB is not configured")
        _driver = AsyncGraphDatabase.driver(uri, auth=(_username(), password))
    return _driver


def _relationship_type(label: str) -> str:
    """Convert an LLM relationship label into a safe Cypher type."""
    value = re.sub(r"[^A-Za-z0-9_]+", "_", (label or "RELATED_TO").strip())
    value = re.sub(r"_+", "_", value).strip("_").upper() or "RELATED_TO"
    if value[0].isdigit():
        value = f"REL_{value}"
    return value[:80]


def _prepare_graph(graph: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, list[dict[str, str]]]]:
    """Validate graph items and group relationships by sanitized Cypher type."""
    nodes: list[dict[str, str]] = []
    node_by_id: dict[str, dict[str, str]] = {}

    for raw in graph.get("nodes", []) or []:
        node_id = str(raw.get("id") or "").strip()
        label = str(raw.get("label") or "").strip()
        entity_type = str(raw.get("type") or "Other").strip() or "Other"
        if not node_id or not label:
            continue
        node = {"source_id": node_id, "label": label, "type": entity_type}
        nodes.append(node)
        node_by_id[node_id] = node

    edges_by_type: dict[str, list[dict[str, str]]] = defaultdict(list)
    for index, raw in enumerate(graph.get("edges", []) or [], start=1):
        source = node_by_id.get(str(raw.get("source") or ""))
        target = node_by_id.get(str(raw.get("target") or ""))
        if source is None or target is None:
            continue
        original_label = str(raw.get("label") or "related_to").strip() or "related_to"
        edges_by_type[_relationship_type(original_label)].append(
            {
                "edge_id": str(raw.get("id") or f"e{index}"),
                "label": original_label,
                "source_label": source["label"],
                "source_type": source["type"],
                "target_label": target["label"],
                "target_type": target["type"],
            }
        )

    return nodes, dict(edges_by_type)


async def ensure_schema() -> None:
    """Create idempotent AuraDB constraints/indexes used by dual-write."""
    global _schema_ready
    if _schema_ready or not is_configured():
        return

    driver = _get_driver()
    async with driver.session(database=_database()) as session:
        await session.run(
            """
            CREATE CONSTRAINT kg_entity_identity IF NOT EXISTS
            FOR (n:Entity)
            REQUIRE (n.user_id, n.label, n.type) IS UNIQUE
            """
        )
        # Relationship types are dynamic, so use a type lookup index instead of
        # a property index that requires a fixed relationship type.
        await session.run(
            """
            CREATE LOOKUP INDEX kg_relationship_type_lookup IF NOT EXISTS
            FOR ()-[r]-() ON EACH type(r)
            """
        )
    _schema_ready = True
    logger.info("Neo4j AuraDB knowledge-graph schema ready")


async def write_document_graph(
    *,
    user_id: str,
    graph_id: str,
    graph: dict[str, Any],
) -> None:
    """Merge one document extract into its owner's cumulative AuraDB graph."""
    if not is_configured():
        raise RuntimeError("Neo4j AuraDB is not configured")

    await ensure_schema()
    nodes, edges_by_type = _prepare_graph(graph)
    driver = _get_driver()

    async with driver.session(database=_database()) as session:
        async with await session.begin_transaction() as tx:
            if nodes:
                await tx.run(
                    """
                    UNWIND $nodes AS item
                    MERGE (n:Entity {
                        user_id: $user_id,
                        label: item.label,
                        type: item.type
                    })
                    ON CREATE SET
                        n.doc_ids = [$graph_id],
                        n.created_at = datetime()
                    ON MATCH SET
                        n.doc_ids = CASE
                            WHEN $graph_id IN coalesce(n.doc_ids, [])
                            THEN n.doc_ids
                            ELSE coalesce(n.doc_ids, []) + $graph_id
                        END
                    SET n.updated_at = datetime()
                    """,
                    nodes=nodes,
                    user_id=user_id,
                    graph_id=graph_id,
                )

            for rel_type, edges in edges_by_type.items():
                # rel_type is generated exclusively by _relationship_type.
                query = f"""
                    UNWIND $edges AS edge
                    MATCH (source:Entity {{
                        user_id: $user_id,
                        label: edge.source_label,
                        type: edge.source_type
                    }})
                    MATCH (target:Entity {{
                        user_id: $user_id,
                        label: edge.target_label,
                        type: edge.target_type
                    }})
                    MERGE (source)-[r:{rel_type} {{
                        user_id: $user_id,
                        doc_id: $graph_id,
                        edge_id: edge.edge_id
                    }}]->(target)
                    SET r.label = edge.label, r.updated_at = datetime()
                """
                await tx.run(
                    query,
                    edges=edges,
                    user_id=user_id,
                    graph_id=graph_id,
                )

            await tx.commit()

    logger.info(
        "AuraDB dual-write complete | user_id=%s graph_id=%s nodes=%s edges=%s",
        user_id,
        graph_id,
        len(nodes),
        sum(len(items) for items in edges_by_type.values()),
    )


async def delete_document_graph(*, user_id: str, graph_id: str) -> None:
    """Remove one document's facts while retaining entities used by other docs."""
    if not is_configured():
        raise RuntimeError("Neo4j AuraDB is not configured")

    await ensure_schema()
    driver = _get_driver()
    async with driver.session(database=_database()) as session:
        async with await session.begin_transaction() as tx:
            await tx.run(
                """
                MATCH ()-[r]-()
                WHERE r.user_id = $user_id AND r.doc_id = $graph_id
                WITH DISTINCT r
                DELETE r
                """,
                user_id=user_id,
                graph_id=graph_id,
            )
            await tx.run(
                """
                MATCH (n:Entity {user_id: $user_id})
                WHERE $graph_id IN coalesce(n.doc_ids, [])
                SET n.doc_ids = [
                    document_id IN n.doc_ids
                    WHERE document_id <> $graph_id
                ],
                n.updated_at = datetime()
                WITH n
                WHERE size(n.doc_ids) = 0
                DETACH DELETE n
                """,
                user_id=user_id,
                graph_id=graph_id,
            )
            await tx.commit()

    logger.info(
        "AuraDB document cleanup complete | user_id=%s graph_id=%s",
        user_id,
        graph_id,
    )


async def verify_connectivity() -> None:
    """Verify configured AuraDB credentials and prepare indexes."""
    if not is_configured():
        raise RuntimeError("Neo4j AuraDB is not configured")
    await _get_driver().verify_connectivity()
    await ensure_schema()


async def close_driver() -> None:
    """Close the shared async driver during application shutdown."""
    global _driver, _schema_ready
    if _driver is not None:
        await _driver.close()
        _driver = None
        _schema_ready = False
