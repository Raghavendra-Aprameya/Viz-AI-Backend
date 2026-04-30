from __future__ import annotations

from typing import Any, Dict, List, Optional


class DSGraphBuilder:
    """Transforms extracted schema JSON into a frontend-friendly graph payload."""

    def __init__(self, db_type: Optional[str] = None):
        self.db_type = (db_type or "unknown").lower()

    def build(self, schema_info: Dict[str, Any]) -> Dict[str, Any]:
        tables = schema_info.get("tables") or []

        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        table_ids: set[str] = set()

        for table in tables:
            table_key = self._table_key(table)
            table_ids.add(table_key)

            columns = table.get("columns") or []
            pk_columns = self._extract_pk_columns(table.get("primary_keys"))

            nodes.append(
                {
                    "id": table_key,
                    "label": table.get("name") or table.get("table") or "unknown_table",
                    "table": table.get("table") or table.get("name") or "unknown_table",
                    "schema": table.get("schema"),
                    "catalog": table.get("catalog"),
                    "column_count": len(columns),
                    "columns": [
                        {
                            "name": c.get("name", "unknown"),
                            "type": str(c.get("type", "unknown")),
                            "is_primary_key": c.get("name") in pk_columns,
                        }
                        for c in columns
                    ],
                    "pk_columns": pk_columns,
                    "meta": {
                        "db_type": self.db_type,
                    },
                }
            )

        for table in tables:
            source_id = self._table_key(table)
            foreign_keys = table.get("foreign_keys") or []

            for index, fk in enumerate(foreign_keys):
                referred_table = fk.get("references")
                if not referred_table:
                    continue

                target_id = self._resolve_target_id(
                    source_table=table,
                    referred_table=referred_table,
                    known_table_ids=table_ids,
                )
                if not target_id:
                    continue

                source_column = fk.get("column") or "unknown_column"
                target_column = fk.get("referred_column") or "id"

                edge_id = f"{source_id}:{source_column}->{target_id}:{target_column}:{index}"
                edges.append(
                    {
                        "id": edge_id,
                        "source": source_id,
                        "target": target_id,
                        "source_column": source_column,
                        "target_column": target_column,
                        "label": f"{source_column} -> {target_column}",
                        "relationship_type": "foreign_key",
                    }
                )

        connected_nodes = {e["source"] for e in edges} | {e["target"] for e in edges}

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "table_count": len(nodes),
                "relation_count": len(edges),
                "orphan_table_count": len([n for n in nodes if n["id"] not in connected_nodes]),
            },
        }

    def _table_key(self, table: Dict[str, Any]) -> str:
        catalog = table.get("catalog")
        schema = table.get("schema")
        name = table.get("table") or table.get("name") or "unknown_table"
        parts = [p for p in [catalog, schema, name] if p]
        return ".".join(parts) if parts else name

    def _extract_pk_columns(self, pk_payload: Any) -> List[str]:
        if not pk_payload:
            return []
        if isinstance(pk_payload, dict):
            constrained = pk_payload.get("constrained_columns")
            if isinstance(constrained, list):
                return [str(c) for c in constrained]
            return []
        return []

    def _resolve_target_id(
        self,
        source_table: Dict[str, Any],
        referred_table: str,
        known_table_ids: set[str],
    ) -> Optional[str]:
        if referred_table in known_table_ids:
            return referred_table

        schema = source_table.get("schema")
        catalog = source_table.get("catalog")

        with_schema = ".".join([p for p in [schema, referred_table] if p])
        with_catalog_schema = ".".join([p for p in [catalog, schema, referred_table] if p])

        for candidate in [with_catalog_schema, with_schema, referred_table]:
            if candidate in known_table_ids:
                return candidate

        return None
