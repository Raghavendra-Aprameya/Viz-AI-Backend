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


_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "by",
        "with",
        "from",
        "at",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "where",
        "when",
        "how",
        "why",
        "show",
        "me",
        "my",
        "our",
        "please",
        "give",
        "get",
        "list",
        "tell",
        "about",
        "vs",
        "versus",
        "chart",
        "graph",
        "plot",
        "data",
    }
)


def extract_question_terms(question: str, *, max_terms: int = 12) -> list[str]:
    """Tokenize a question into lowercase search terms (stopwords removed)."""
    raw = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{1,}", question or "")
    terms: list[str] = []
    seen: set[str] = set()
    for token in raw:
        value = token.lower()
        if value in _STOPWORDS or value in seen:
            continue
        seen.add(value)
        terms.append(value)
        if len(terms) >= max_terms:
            break
    return terms


def subgraph_to_context(
    nodes: list[dict[str, str]],
    edges: list[dict[str, str]],
) -> str:
    """Serialize a 1-hop subgraph into prompt context (nodes + edges only)."""
    if not nodes and not edges:
        return (
            "[KNOWLEDGE GRAPH CONTEXT]\n"
            "No matching entities or relationships were found for this question.\n"
        )

    entity_lines = [
        f"- {n['label']} ({n.get('type') or 'Other'})"
        for n in nodes
        if n.get("label")
    ]
    rel_lines = [
        f"- {e['source']} -[{e['label']}]-> {e['target']}"
        for e in edges
        if e.get("source") and e.get("target")
    ]
    fact_lines = [
        f"- {e['source']} {str(e.get('label') or 'related to').replace('_', ' ')} {e['target']}"
        for e in edges
        if e.get("source") and e.get("target")
    ]

    parts = [
        "[KNOWLEDGE GRAPH CONTEXT]",
        "Use only these facts. Do not invent entities or relationships.",
        "",
        "Entities:",
        *(entity_lines or ["- (none)"]),
        "",
        "Relationships:",
        *(rel_lines or ["- (none)"]),
        "",
        "Derived facts:",
        *(fact_lines or ["- (none)"]),
    ]
    return "\n".join(parts) + "\n"


async def query_user_subgraph(
    *,
    user_id: str,
    terms: list[str],
    max_nodes: int = 30,
    max_edges: int = 50,
) -> dict[str, Any]:
    """
    Fetch a 1-hop subgraph for one user filtered by case-insensitive label terms.

    Returns ``{"nodes": [...], "edges": [...]}`` with label/type (and source/target
    labels on edges). Does not include document file content.
    """
    if not is_configured():
        raise RuntimeError("Neo4j AuraDB is not configured")

    cleaned_terms = [t.strip().lower() for t in terms if t and t.strip()]
    if not cleaned_terms:
        return {"nodes": [], "edges": []}

    await ensure_schema()
    driver = _get_driver()

    async with driver.session(database=_database()) as session:
        result = await session.run(
            """
            MATCH (n:Entity {user_id: $user_id})
            WHERE any(term IN $terms WHERE toLower(n.label) CONTAINS term)
            WITH n
            LIMIT $seed_limit
            OPTIONAL MATCH (n)-[r]-(m:Entity {user_id: $user_id})
            WHERE r.user_id = $user_id
            RETURN
              n.label AS n_label,
              n.type AS n_type,
              m.label AS m_label,
              m.type AS m_type,
              CASE WHEN r IS NULL THEN null ELSE coalesce(r.label, type(r)) END AS rel_label,
              CASE WHEN r IS NULL THEN null ELSE startNode(r).label END AS start_label,
              CASE WHEN r IS NULL THEN null ELSE endNode(r).label END AS end_label
            LIMIT $row_limit
            """,
            user_id=user_id,
            terms=cleaned_terms,
            seed_limit=max_nodes,
            row_limit=max(max_nodes * 4, max_edges * 2),
        )
        rows = [record.data() async for record in result]

    nodes_by_key: dict[tuple[str, str], dict[str, str]] = {}
    edges: list[dict[str, str]] = []
    edge_keys: set[tuple[str, str, str]] = set()

    def _add_node(label: str | None, entity_type: str | None) -> None:
        if not label:
            return
        node_type = (entity_type or "Other").strip() or "Other"
        key = (label, node_type)
        if key not in nodes_by_key and len(nodes_by_key) < max_nodes:
            nodes_by_key[key] = {"label": label, "type": node_type}

    for row in rows:
        _add_node(row.get("n_label"), row.get("n_type"))
        _add_node(row.get("m_label"), row.get("m_type"))
        source = row.get("start_label")
        target = row.get("end_label")
        rel = (row.get("rel_label") or "").strip()
        if not source or not target or not rel:
            continue
        edge_key = (source, rel, target)
        if edge_key in edge_keys or len(edges) >= max_edges:
            continue
        edge_keys.add(edge_key)
        edges.append({"source": source, "label": rel, "target": target})

    nodes = list(nodes_by_key.values())
    logger.info(
        "AuraDB subgraph query | user_id=%s terms=%s nodes=%s edges=%s",
        user_id,
        cleaned_terms,
        len(nodes),
        len(edges),
    )
    return {"nodes": nodes, "edges": edges}


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
