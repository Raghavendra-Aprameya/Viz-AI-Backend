import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import httpx
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.schema_models import (
    DatabaseConnectionModel,
    OntologyEnrichmentSessionModel,
    OntologyVersionModel,
)
from app.utils.constants import Permissions as Permission
from app.utils.access import require_permission

logger = logging.getLogger(__name__)


def _safe_json_loads(value: Optional[str], fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _normalize_free_text(value: str) -> str:
    """
    Lightweight normalization for enrichment text answers.
    Handles common typos and sentence casing without hard failing.
    """
    if not value:
        return value

    text = " ".join(str(value).strip().split())
    if not text:
        return text

    typo_map = {
        "reenue": "revenue",
        "revnue": "revenue",
        "averge": "average",
        "avrage": "average",
        "defne": "define",
        "sumof": "sum of",
        "peryear": "per year",
    }

    tokens = text.split(" ")
    normalized_tokens = []
    for token in tokens:
        raw = token
        low = raw.lower()
        # preserve trailing punctuation
        punct = ""
        if low and low[-1] in {".", ",", ";", ":"}:
            punct = low[-1]
            low = low[:-1]
        rep = typo_map.get(low, low)
        normalized_tokens.append(rep + punct)

    text = " ".join(normalized_tokens)
    text = text[0].upper() + text[1:] if text else text
    if text and text[-1] not in {".", "!", "?"}:
        text += "."
    return text


async def _llm_normalize_free_text(value: str, purpose: str) -> str:
    """
    Optional LLM-based text normalization for user enrichment answers.
    Falls back to heuristic normalization if endpoint is unavailable.
    """
    fallback = _normalize_free_text(value)
    endpoint = os.getenv("ONTOLOGY_TEXT_NORMALIZER_URL", "http://127.0.0.1:8001/api/ontology/normalize-text")
    timeout_seconds = float(os.getenv("ONTOLOGY_TEXT_NORMALIZER_TIMEOUT", "10"))
    payload = {
        "text": value,
        "purpose": purpose,
        "instructions": "Correct spelling and grammar only. Keep original meaning.",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(endpoint, json=payload)
            response.raise_for_status()
            data = response.json()
        normalized = data.get("text") if isinstance(data, dict) else None
        if isinstance(normalized, str) and normalized.strip():
            return _normalize_free_text(normalized.strip())
    except Exception:
        pass
    return fallback


async def _llm_enrichment_chat(
    ontology: Dict[str, Any],
    chat_history: List[Dict[str, str]],
    user_message: str,
    thread_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ask LLM to continue enrichment chat and extract structured updates.
    """
    endpoint = os.getenv("ONTOLOGY_ENRICHMENT_CHAT_URL", "http://127.0.0.1:8001/api/ontology/enrichment-chat")
    timeout_seconds = float(os.getenv("ONTOLOGY_ENRICHMENT_CHAT_TIMEOUT", "20"))
    payload = {
        "ontology": ontology,
        "chat_history": chat_history,
        "user_message": user_message,
        "thread_id": thread_id,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.post(endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, dict) and isinstance(data.get("assistant_message"), str):
            return data
    except Exception as exc:
        logger.warning("LLM enrichment chat fallback: %s", str(exc))

    # Fallback reply: keep conversation moving even if LLM chat endpoint is unavailable.
    return {
        "assistant_message": "Thanks, I captured that. You can continue adding business definitions or click Apply Enrichment.",
        "extracted_updates": {},
    }


def _iri_safe(raw: str) -> str:
    base = "".join(ch if ch.isalnum() else "_" for ch in (raw or "Thing"))
    return base.strip("_") or "Thing"


def _split_words(raw: str) -> List[str]:
    if not raw:
        return []
    # split snake_case, kebab-case, dots, camelCase
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(raw))
    s = re.sub(r"[^A-Za-z0-9]+", " ", s)
    return [w.lower() for w in s.split() if w]


def _to_class_name(raw: str) -> str:
    name = raw.split(".")[-1]
    clean = "".join(ch if ch.isalnum() else " " for ch in name)
    return "".join(part.capitalize() for part in clean.split()) or "Entity"


def _to_relation_label(source_column: str, target_table: str) -> str:
    """
    Generic relation naming from FK column and target entity.
    Avoids domain hardcoding (customer/seller/etc.).
    """
    words = _split_words(source_column)
    # Drop very common FK suffixes/prefixes for cleaner property names.
    stop = {"id", "pk", "fk", "key", "uuid", "guid", "ref", "code"}
    core = [w for w in words if w not in stop]
    if core:
        base = "".join(w.capitalize() for w in core)
        if base:
            return f"has{base}"
    return f"relatedTo{_to_class_name(target_table)}"


def _is_date_like(column_name: str, column_type: str) -> bool:
    words = _split_words(column_name)
    ctype = (column_type or "").lower()
    generic_terms = {"date", "time", "timestamp", "datetime", "created", "updated", "modified"}
    return bool(set(words) & generic_terms) or any(k in ctype for k in ["date", "time"])


def _is_revenue_like(column_name: str) -> bool:
    words = _split_words(column_name)
    generic_terms = {"revenue", "amount", "payment", "price", "total", "value", "cost", "sales", "income"}
    return bool(set(words) & generic_terms)


def _build_base_ontology(db_connection: DatabaseConnectionModel) -> Dict[str, Any]:
    ds_graph = _safe_json_loads(db_connection.ds_graph_json, {"nodes": [], "edges": [], "stats": {}})
    schema = _safe_json_loads(db_connection.db_schema, {"tables": []})

    class_nodes = []
    relationships = []
    attributes = []

    for node in ds_graph.get("nodes", []):
        class_name = _to_class_name(node.get("table") or node.get("label") or node.get("id"))
        class_nodes.append(
            {
                "id": node.get("id"),
                "name": class_name,
                "table": node.get("table") or node.get("label"),
                "schema": node.get("schema"),
                "column_count": node.get("column_count", 0),
            }
        )
        for col in node.get("columns", []):
            attributes.append(
                {
                    "class_id": node.get("id"),
                    "name": col.get("name"),
                    "type": col.get("type"),
                    "is_primary_key": bool(col.get("is_primary_key")),
                }
            )

    seen_pair_edges = set()
    for edge in ds_graph.get("edges", []):
        source = edge.get("source")
        target = edge.get("target")
        if not source or not target:
            continue
        pair_key = (source, target)
        if pair_key in seen_pair_edges:
            # Keep ontology graph clean: one semantic edge per table-pair for default view.
            continue
        seen_pair_edges.add(pair_key)
        relationships.append(
            {
                "id": edge.get("id"),
                "source": source,
                "target": target,
                "source_column": edge.get("source_column"),
                "target_column": edge.get("target_column"),
                "label": _to_relation_label(edge.get("source_column", ""), target),
                "relationship_type": edge.get("relationship_type", "foreign_key"),
            }
        )

    ontology = {
        "metadata": {
            "datasource_connection_id": str(db_connection.id),
            "db_type": db_connection.db_type,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "schema_table_count": len(schema.get("tables", [])),
        },
        "classes": class_nodes,
        "relationships": relationships,
        "attributes": attributes,
        "metrics": [],
        "aliases": [],
        "rules": {
            "default_filters": {},
            "default_time_dimension": None,
            "status_success_values": [],
        },
    }

    return ontology


def _merge_refined_with_canonical_mappings(
    canonical: Dict[str, Any],
    refined: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Keep technical schema mappings stable while allowing LLM-friendly business text.
    This prevents NL2SQL/graph regressions from accidental id/source/target rewrites.
    """
    if not isinstance(canonical, dict):
        return refined if isinstance(refined, dict) else {}
    if not isinstance(refined, dict):
        return canonical

    out = dict(canonical)
    out["metadata"] = refined.get("metadata", canonical.get("metadata", {})) if isinstance(refined.get("metadata"), dict) else canonical.get("metadata", {})
    out["rules"] = refined.get("rules", canonical.get("rules", {})) if isinstance(refined.get("rules"), dict) else canonical.get("rules", {})
    out["metrics"] = refined.get("metrics", canonical.get("metrics", [])) if isinstance(refined.get("metrics"), list) else canonical.get("metrics", [])
    out["aliases"] = refined.get("aliases", canonical.get("aliases", [])) if isinstance(refined.get("aliases"), list) else canonical.get("aliases", [])

    canonical_classes = canonical.get("classes", []) if isinstance(canonical.get("classes"), list) else []
    refined_class_by_id = {
        str(c.get("id")): c for c in (refined.get("classes", []) if isinstance(refined.get("classes"), list) else []) if isinstance(c, dict) and c.get("id")
    }
    merged_classes = []
    for c in canonical_classes:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id"))
        rc = refined_class_by_id.get(cid, {})
        merged = dict(c)
        if isinstance(rc.get("name"), str) and rc.get("name").strip():
            merged["name"] = rc["name"].strip()
        if isinstance(rc.get("description"), str) and rc.get("description").strip():
            merged["description"] = rc["description"].strip()
        merged_classes.append(merged)
    out["classes"] = merged_classes

    canonical_relationships = canonical.get("relationships", []) if isinstance(canonical.get("relationships"), list) else []
    refined_rel_by_id = {
        str(r.get("id")): r for r in (refined.get("relationships", []) if isinstance(refined.get("relationships"), list) else []) if isinstance(r, dict) and r.get("id")
    }
    merged_relationships = []
    for r in canonical_relationships:
        if not isinstance(r, dict):
            continue
        rid = str(r.get("id"))
        rr = refined_rel_by_id.get(rid, {})
        merged = dict(r)
        if isinstance(rr.get("label"), str) and rr.get("label").strip():
            merged["label"] = rr["label"].strip()
        if isinstance(rr.get("description"), str) and rr.get("description").strip():
            merged["description"] = rr["description"].strip()
        merged_relationships.append(merged)
    out["relationships"] = merged_relationships

    canonical_attributes = canonical.get("attributes", []) if isinstance(canonical.get("attributes"), list) else []
    refined_attrs = refined.get("attributes", []) if isinstance(refined.get("attributes"), list) else []
    refined_attr_by_key = {}
    for a in refined_attrs:
        if not isinstance(a, dict):
            continue
        key = f"{a.get('class_id')}::{a.get('name')}"
        refined_attr_by_key[key] = a
    merged_attributes = []
    for a in canonical_attributes:
        if not isinstance(a, dict):
            continue
        key = f"{a.get('class_id')}::{a.get('name')}"
        ra = refined_attr_by_key.get(key, {})
        merged = dict(a)
        if isinstance(ra.get("description"), str) and ra.get("description").strip():
            merged["description"] = ra["description"].strip()
        merged_attributes.append(merged)
    out["attributes"] = merged_attributes
    return out


async def _llm_refine_ontology(
    ontology: Dict[str, Any],
    db_schema_json: Optional[str],
    db_type: Optional[str],
    timeout_seconds: float = 20.0,
) -> Dict[str, Any]:
    """
    Optional LLM-assisted refinement.
    Fallback-safe: returns original ontology if LLM is unavailable or invalid.
    """
    llm_endpoint = os.getenv("ONTOLOGY_REFINER_URL", "http://127.0.0.1:8001/api/ontology/refine")
    timeout_seconds = float(os.getenv("ONTOLOGY_REFINER_TIMEOUT", str(timeout_seconds)))
    payload = {
        "db_type": db_type or "unknown",
        "db_schema": db_schema_json or "{}",
        "ontology": ontology,
        "instructions": (
            "Refine ontology names and relationship labels to business-friendly terms. "
            "Keep schema compatibility. Return JSON object only."
        ),
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(llm_endpoint, json=payload)
            response.raise_for_status()
            data = response.json()

        refined = data.get("ontology") if isinstance(data, dict) else None
        if not isinstance(refined, dict):
            return ontology

        # Minimal shape checks
        if not isinstance(refined.get("classes"), list) or not isinstance(refined.get("relationships"), list):
            return ontology

        refined.setdefault("metadata", {})
        refined["metadata"]["llm_refined"] = True
        refined["metadata"]["llm_refined_at"] = datetime.now(timezone.utc).isoformat()
        return refined
    except Exception as exc:
        logger.warning("LLM ontology refinement skipped: %s", str(exc))
        ontology.setdefault("metadata", {})
        ontology["metadata"]["llm_refined"] = False
        return ontology


def _ontology_to_graph(ontology: Dict[str, Any]) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    for cls in ontology.get("classes", []):
        nodes.append(
            {
                "id": cls["id"],
                "label": cls["name"],
                "type": "class",
                "meta": {
                    "table": cls.get("table"),
                    "schema": cls.get("schema"),
                    "column_count": cls.get("column_count", 0),
                },
            }
        )

    for metric in ontology.get("metrics", []):
        metric_id = metric.get("id") or f"metric:{metric.get('name', 'metric')}"
        nodes.append(
            {
                "id": metric_id,
                "label": metric.get("name", "Metric"),
                "type": "metric",
                "meta": {"definition": metric.get("definition"), "formula": metric.get("formula")},
            }
        )
        base_class = metric.get("based_on_class")
        if base_class:
            edges.append(
                {
                    "id": f"{metric_id}->{base_class}",
                    "source": metric_id,
                    "target": base_class,
                    "label": "based on",
                    "type": "metric_link",
                    "meta": {},
                }
            )

    for rel in ontology.get("relationships", []):
        edges.append(
            {
                "id": rel["id"],
                "source": rel["source"],
                "target": rel["target"],
                "label": rel.get("label") or rel.get("relationship_type", "relation"),
                "type": rel.get("relationship_type", "foreign_key"),
                "meta": {
                    "source_column": rel.get("source_column"),
                    "target_column": rel.get("target_column"),
                },
            }
        )

    stats = {
        "class_count": len([n for n in nodes if n["type"] == "class"]),
        "metric_count": len([n for n in nodes if n["type"] == "metric"]),
        "relation_count": len(edges),
    }

    return {"nodes": nodes, "edges": edges, "stats": stats}


def _ontology_to_ttl(ontology: Dict[str, Any]) -> str:
    """
    Convert internal ontology JSON to Turtle.
    Uses rdflib when available, falls back to manual Turtle.
    """
    try:
        from rdflib import Graph, Namespace, RDF, RDFS, OWL, XSD, Literal, URIRef

        ex = Namespace("http://vizai.ai/ontology#")
        g = Graph()
        g.bind("ex", ex)
        g.bind("owl", OWL)
        g.bind("rdfs", RDFS)
        g.bind("xsd", XSD)

        class_map: Dict[str, URIRef] = {}
        for cls in ontology.get("classes", []):
            cid = cls.get("id", "")
            cname = _iri_safe(cls.get("name") or cls.get("table") or cid)
            c_uri = ex[cname]
            class_map[cid] = c_uri
            g.add((c_uri, RDF.type, OWL.Class))

        for rel in ontology.get("relationships", []):
            src = class_map.get(rel.get("source", ""), ex[_iri_safe(rel.get("source", "Source"))])
            tgt = class_map.get(rel.get("target", ""), ex[_iri_safe(rel.get("target", "Target"))])
            rel_id = str(rel.get("id") or "")
            rel_label = str(rel.get("label") or rel.get("relationship_type") or "relatedTo")
            # Keep each relationship as its own property in OWL to avoid domain/range collapsing
            # when multiple edges share the same label (e.g., many "hasItem" relations).
            prop_key = f"{_iri_safe(rel_label)}_{_iri_safe(rel_id)}" if rel_id else _iri_safe(rel_label)
            prop = ex[prop_key]
            g.add((prop, RDF.type, OWL.ObjectProperty))
            g.add((prop, RDFS.domain, src))
            g.add((prop, RDFS.range, tgt))
            g.add((prop, RDFS.label, Literal(rel_label)))

        for attr in ontology.get("attributes", []):
            src = class_map.get(attr.get("class_id", ""), ex[_iri_safe(attr.get("class_id", "Entity"))])
            prop = ex[_iri_safe(attr.get("name", "attribute"))]
            dtype_raw = str(attr.get("type", "")).lower()
            dtype = XSD.string
            if any(k in dtype_raw for k in ["int", "number"]):
                dtype = XSD.integer
            elif any(k in dtype_raw for k in ["float", "double", "decimal", "numeric"]):
                dtype = XSD.decimal
            elif any(k in dtype_raw for k in ["date", "time"]):
                dtype = XSD.dateTime
            g.add((prop, RDF.type, OWL.DatatypeProperty))
            g.add((prop, RDFS.domain, src))
            g.add((prop, RDFS.range, dtype))

        for metric in ontology.get("metrics", []):
            mid = ex[_iri_safe(metric.get("name", "Metric"))]
            g.add((mid, RDF.type, ex.BusinessMetric))
            if metric.get("definition"):
                g.add((mid, ex.definition, Literal(str(metric["definition"]))))
            if metric.get("formula"):
                g.add((mid, ex.formula, Literal(str(metric["formula"]))))

        return g.serialize(format="turtle")
    except Exception:
        # Fallback to manual Turtle if rdflib is unavailable.
        pass

    lines: List[str] = [
        "@prefix ex: <http://vizai.ai/ontology#> .",
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
    ]

    class_map: Dict[str, str] = {}
    for cls in ontology.get("classes", []):
        cid = cls.get("id", "")
        cname = _iri_safe(cls.get("name") or cls.get("table") or cid)
        class_map[cid] = cname
        lines.append(f"ex:{cname} a owl:Class .")

    lines.append("")

    for rel in ontology.get("relationships", []):
        src = class_map.get(rel.get("source", ""), _iri_safe(rel.get("source", "Source")))
        tgt = class_map.get(rel.get("target", ""), _iri_safe(rel.get("target", "Target")))
        rel_id = str(rel.get("id") or "")
        rel_label = str(rel.get("label") or rel.get("relationship_type") or "relatedTo")
        prop = f"{_iri_safe(rel_label)}_{_iri_safe(rel_id)}" if rel_id else _iri_safe(rel_label)
        safe_label = rel_label.replace('"', '\\"')
        lines.append(
            f'ex:{prop} a owl:ObjectProperty ; rdfs:domain ex:{src} ; rdfs:range ex:{tgt} ; rdfs:label "{safe_label}" .'
        )

    lines.append("")

    for attr in ontology.get("attributes", []):
        src = class_map.get(attr.get("class_id", ""), _iri_safe(attr.get("class_id", "Entity")))
        prop = _iri_safe(attr.get("name", "attribute"))
        dtype_raw = str(attr.get("type", "")).lower()
        dtype = "xsd:string"
        if any(k in dtype_raw for k in ["int", "number"]):
            dtype = "xsd:integer"
        elif any(k in dtype_raw for k in ["float", "double", "decimal", "numeric"]):
            dtype = "xsd:decimal"
        elif any(k in dtype_raw for k in ["date", "time"]):
            dtype = "xsd:dateTime"
        lines.append(f"ex:{prop} a owl:DatatypeProperty ; rdfs:domain ex:{src} ; rdfs:range {dtype} .")

    lines.append("")

    for metric in ontology.get("metrics", []):
        mid = _iri_safe(metric.get("name", "Metric"))
        definition = str(metric.get("definition", "")).replace('"', '\\"')
        formula = str(metric.get("formula", "")).replace('"', '\\"')
        lines.append(f"ex:{mid} a ex:BusinessMetric .")
        if definition:
            lines.append(f'ex:{mid} ex:definition "{definition}" .')
        if formula:
            lines.append(f'ex:{mid} ex:formula "{formula}" .')

    return "\n".join(lines)


def _extract_candidate_columns(ontology: Dict[str, Any]) -> Dict[str, List[str]]:
    date_candidates: List[str] = []
    revenue_candidates: List[str] = []
    status_candidates: List[str] = []

    for attr in ontology.get("attributes", []):
        name = attr.get("name", "")
        col_type = str(attr.get("type", ""))
        if _is_date_like(name, col_type):
            date_candidates.append(name)
        if _is_revenue_like(name):
            revenue_candidates.append(name)
        if "status" in name.lower() or "state" in name.lower():
            status_candidates.append(name)

    return {
        "date": sorted(set(date_candidates)),
        "revenue": sorted(set(revenue_candidates)),
        "status": sorted(set(status_candidates)),
    }


def _generate_dynamic_questions(ontology: Dict[str, Any], db_type: Optional[str]) -> List[Dict[str, Any]]:
    candidates = _extract_candidate_columns(ontology)
    questions: List[Dict[str, Any]] = []

    if len(candidates["date"]) > 1:
        questions.append(
            {
                "question_id": "default_date_dimension",
                "target_term": "rules.default_time_dimension",
                "question": "Which date/time column should be used by default for business trends?",
                "reason": "Multiple date-like columns were found.",
                "answer_type": "single_select",
                "options": candidates["date"][:8],
                "priority": 10,
            }
        )
        questions.append(
            {
                "question_id": "default_time_granularity",
                "target_term": "rules.default_time_granularity",
                "question": "What default time granularity should we use in trends?",
                "reason": "Choosing day/week/month improves consistent chart outputs.",
                "answer_type": "single_select",
                "options": ["day", "week", "month", "quarter"],
                "priority": 12,
            }
        )

    if len(candidates["revenue"]) > 0:
        questions.append(
            {
                "question_id": "average_revenue_formula",
                "target_term": "metrics.AverageRevenue",
                "question": "How should we define Average Revenue for this datasource?",
                "reason": "Revenue-like columns were detected; definition varies by business.",
                "answer_type": "text",
                "options": [],
                "priority": 20,
            }
        )
        questions.append(
            {
                "question_id": "average_revenue_denominator",
                "target_term": "metrics.AverageRevenue.denominator",
                "question": "Average revenue should be calculated per what unit?",
                "reason": "Different businesses define average revenue differently.",
                "answer_type": "single_select",
                "options": ["order", "customer", "product", "seller"],
                "priority": 22,
            }
        )

    if len(candidates["status"]) > 0:
        questions.append(
            {
                "question_id": "success_status_values",
                "target_term": "rules.status_success_values",
                "question": "Which status values should count as successful records?",
                "reason": "Status column(s) detected and this impacts business metrics.",
                "answer_type": "text",
                "options": [],
                "priority": 30,
            }
        )

    questions.append(
        {
            "question_id": "exclude_test_data",
            "target_term": "rules.default_filters",
            "question": "Do you want to exclude any test/internal data by default?",
            "reason": "Default quality filters improve query consistency.",
            "answer_type": "text",
            "options": [],
            "priority": 40,
        }
    )

    if (db_type or "").lower() == "salesforce":
        questions.append(
            {
                "question_id": "salesforce_deleted_filter",
                "target_term": "rules.default_filters.IsDeleted",
                "question": "Should records with IsDeleted=true be excluded by default?",
                "reason": "Salesforce objects commonly include soft-deleted records.",
                "answer_type": "single_select",
                "options": ["Yes", "No"],
                "priority": 15,
            }
        )

    return sorted(questions, key=lambda q: q.get("priority", 100))


async def _apply_answers_to_ontology(ontology: Dict[str, Any], answers: Dict[str, Any]) -> Dict[str, Any]:
    updated = json.loads(json.dumps(ontology))

    default_date = answers.get("default_date_dimension")
    if isinstance(default_date, str) and default_date.strip():
        updated.setdefault("rules", {})["default_time_dimension"] = default_date.strip()

    default_grain = answers.get("default_time_granularity")
    if isinstance(default_grain, str) and default_grain.strip():
        updated.setdefault("rules", {})["default_time_granularity"] = default_grain.strip()

    success_values = answers.get("success_status_values")
    if isinstance(success_values, str) and success_values.strip():
        normalized_status_text = await _llm_normalize_free_text(success_values, "status_values")
        split_values = [v.strip() for v in normalized_status_text.replace(";", ",").replace(".", "").split(",") if v.strip()]
        updated.setdefault("rules", {})["status_success_values"] = split_values

    exclude_data = answers.get("exclude_test_data")
    if isinstance(exclude_data, str) and exclude_data.strip():
        cleaned = await _llm_normalize_free_text(exclude_data, "default_filter")
        updated.setdefault("rules", {}).setdefault("default_filters", {})["custom"] = cleaned

    sf_deleted = answers.get("salesforce_deleted_filter")
    if isinstance(sf_deleted, str):
        flag = sf_deleted.strip().lower() == "yes"
        updated.setdefault("rules", {}).setdefault("default_filters", {})["IsDeleted"] = (
            "exclude_true" if flag else "include_all"
        )

    avg_revenue_formula = answers.get("average_revenue_formula")
    avg_revenue_denominator = answers.get("average_revenue_denominator")
    if isinstance(avg_revenue_formula, str) and avg_revenue_formula.strip():
        cleaned_formula = await _llm_normalize_free_text(avg_revenue_formula, "metric_formula")
        metrics = updated.setdefault("metrics", [])
        existing = next((m for m in metrics if m.get("name") == "AverageRevenue"), None)
        metric_payload = {
            "id": "metric:AverageRevenue",
            "name": "AverageRevenue",
            "definition": "Business-defined average revenue metric",
            "formula": cleaned_formula,
            "denominator": avg_revenue_denominator if isinstance(avg_revenue_denominator, str) else None,
            "based_on_class": (updated.get("classes") or [{}])[0].get("id") if updated.get("classes") else None,
        }
        if existing:
            existing.update(metric_payload)
        else:
            metrics.append(metric_payload)
        aliases = updated.setdefault("aliases", [])
        for alias in ["average revenue", "avg revenue", "arpu"]:
            if not any(a.get("alias") == alias for a in aliases):
                aliases.append({"alias": alias, "maps_to": "AverageRevenue"})

    updated.setdefault("metadata", {})["last_enriched_at"] = datetime.now(timezone.utc).isoformat()
    return updated


def _get_connection_or_404(db: Session, connection_id: UUID) -> DatabaseConnectionModel:
    connection = db.query(DatabaseConnectionModel).filter(DatabaseConnectionModel.id == connection_id).first()
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Database connection not found")
    if not connection.ds_graph_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Datasource graph not available yet. Please complete schema extraction first.",
        )
    return connection


def _get_latest_ontology_version(db: Session, connection_id: UUID) -> Optional[OntologyVersionModel]:
    return (
        db.query(OntologyVersionModel)
        .filter(OntologyVersionModel.datasource_connection_id == connection_id)
        .order_by(OntologyVersionModel.version_number.desc())
        .first()
    )


@require_permission(Permission.VIEW_DATASOURCE)
async def get_latest_ontology(connection_id: UUID, db: Session = Depends(get_db), token_payload: dict = None):
    _get_connection_or_404(db, connection_id)
    version = _get_latest_ontology_version(db, connection_id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ontology not built yet")

    graph_payload = _safe_json_loads(version.graph_json, {"nodes": [], "edges": [], "stats": {}})
    ontology_payload = _safe_json_loads(version.ontology_json, {})

    return {
        "ontology_version_id": str(version.id),
        "version_label": version.version_label,
        "status": version.status,
        "is_base": bool(version.is_base),
        "graph": graph_payload,
        "ontology": ontology_payload,
    }


@require_permission(Permission.VIEW_DATASOURCE)
async def get_latest_ontology_ttl(connection_id: UUID, db: Session = Depends(get_db), token_payload: dict = None):
    _get_connection_or_404(db, connection_id)
    version = _get_latest_ontology_version(db, connection_id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ontology not built yet")

    ttl = version.ontology_ttl
    if not ttl:
        ontology_payload = _safe_json_loads(version.ontology_json, {})
        ttl = _ontology_to_ttl(ontology_payload)
        version.ontology_ttl = ttl
        db.commit()
    return ttl


@require_permission(Permission.VIEW_DATASOURCE)
async def validate_latest_ontology_ttl(connection_id: UUID, db: Session = Depends(get_db), token_payload: dict = None):
    """
    Lightweight Turtle validation for current ontology snapshot.
    """
    ttl = await get_latest_ontology_ttl(connection_id, db, token_payload)
    lines = [ln.strip() for ln in ttl.splitlines() if ln.strip()]
    errors: List[str] = []

    required_prefixes = [
        "@prefix ex:",
        "@prefix owl:",
        "@prefix rdfs:",
    ]
    for p in required_prefixes:
        if not any(ln.startswith(p) for ln in lines):
            errors.append(f"Missing required prefix: {p}")

    triple_lines = [ln for ln in lines if not ln.startswith("@prefix")]
    if not triple_lines:
        errors.append("No triples found in TTL body.")

    malformed = [ln for ln in triple_lines if not ln.endswith(".")]
    if malformed:
        errors.append(f"{len(malformed)} triple line(s) do not end with '.'.")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "triple_count": len(triple_lines),
    }


@require_permission(Permission.EDIT_DATASOURCE)
async def bootstrap_ontology(connection_id: UUID, db: Session = Depends(get_db), token_payload: dict = None):
    db_connection = _get_connection_or_404(db, connection_id)
    latest = _get_latest_ontology_version(db, connection_id)
    if latest:
        return await get_latest_ontology(connection_id, db, token_payload)

    ontology = _build_base_ontology(db_connection)
    ontology = await _llm_refine_ontology(
        ontology=ontology,
        db_schema_json=db_connection.db_schema,
        db_type=db_connection.db_type,
    )
    graph = _ontology_to_graph(ontology)

    user_id = token_payload.get("sub") if token_payload else None

    version = OntologyVersionModel(
        id=uuid4(),
        datasource_connection_id=connection_id,
        version_number=1,
        version_label="base_v1",
        status="published",
        is_base=True,
        ontology_json=json.dumps(ontology),
        ontology_ttl=_ontology_to_ttl(ontology),
        graph_json=json.dumps(graph),
        created_by=UUID(user_id) if user_id else None,
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    return {
        "ontology_version_id": str(version.id),
        "version_label": version.version_label,
        "status": version.status,
        "is_base": bool(version.is_base),
        "graph": graph,
        "ontology": ontology,
    }


@require_permission(Permission.EDIT_DATASOURCE)
async def start_enrichment(connection_id: UUID, db: Session = Depends(get_db), token_payload: dict = None):
    await bootstrap_ontology(connection_id, db, token_payload)
    base_version = _get_latest_ontology_version(db, connection_id)
    if not base_version:
        raise HTTPException(status_code=500, detail="Failed to prepare base ontology")

    ontology = _safe_json_loads(base_version.ontology_json, {})

    user_id = token_payload.get("sub") if token_payload else None

    initial_message = (
        "Ontology enrichment chat started. "
        "Tell me your metric definitions, default date dimension/granularity, status meanings, "
        "and any default filters. You can ask follow-up questions too."
    )
    initial_state = {
        "chat_history": [{"role": "assistant", "content": initial_message}],
        "updates": {},
    }

    session = OntologyEnrichmentSessionModel(
        id=uuid4(),
        datasource_connection_id=connection_id,
        base_ontology_version_id=base_version.id,
        status="in_progress",
        questions_json=json.dumps({"mode": "chat"}),
        answers_json=json.dumps(initial_state),
        created_by=UUID(user_id) if user_id else None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return {
        "session_id": str(session.id),
        "ontology_version_id": str(base_version.id),
        "initial_message": initial_message,
    }


@require_permission(Permission.EDIT_DATASOURCE)
async def enrichment_chat_message(
    connection_id: UUID,
    session_id: UUID,
    message: str,
    db: Session = Depends(get_db),
    token_payload: dict = None,
):
    _get_connection_or_404(db, connection_id)
    session = (
        db.query(OntologyEnrichmentSessionModel)
        .filter(
            OntologyEnrichmentSessionModel.id == session_id,
            OntologyEnrichmentSessionModel.datasource_connection_id == connection_id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Enrichment session not found")
    if session.status != "in_progress":
        raise HTTPException(status_code=400, detail="Enrichment session is not active")

    base_version = db.query(OntologyVersionModel).filter(OntologyVersionModel.id == session.base_ontology_version_id).first()
    if not base_version:
        raise HTTPException(status_code=404, detail="Base ontology version not found")

    state = _safe_json_loads(session.answers_json, {"chat_history": [], "updates": {}})
    chat_history = state.get("chat_history", [])
    updates = state.get("updates", {})

    chat_history.append({"role": "user", "content": message})
    ontology = _safe_json_loads(base_version.ontology_json, {})
    llm_resp = await _llm_enrichment_chat(ontology, chat_history, message, str(session_id))
    assistant_message = llm_resp.get("assistant_message") or "Noted."
    extracted_updates = llm_resp.get("extracted_updates") or {}

    if isinstance(extracted_updates, dict):
        updates.update(extracted_updates)
    chat_history.append({"role": "assistant", "content": assistant_message})

    session.answers_json = json.dumps({"chat_history": chat_history, "updates": updates})
    db.commit()

    return {
        "session_id": str(session.id),
        "assistant_message": assistant_message,
        "extracted_updates": updates,
        "chat_history": chat_history,
    }


@require_permission(Permission.EDIT_DATASOURCE)
async def submit_enrichment_answers(
    connection_id: UUID,
    session_id: UUID,
    answers: List[Dict[str, Any]],
    db: Session = Depends(get_db),
    token_payload: dict = None,
):
    db_connection = _get_connection_or_404(db, connection_id)

    session = (
        db.query(OntologyEnrichmentSessionModel)
        .filter(
            OntologyEnrichmentSessionModel.id == session_id,
            OntologyEnrichmentSessionModel.datasource_connection_id == connection_id,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Enrichment session not found")

    base_version = db.query(OntologyVersionModel).filter(OntologyVersionModel.id == session.base_ontology_version_id).first()
    if not base_version:
        raise HTTPException(status_code=404, detail="Base ontology version not found")

    state = _safe_json_loads(session.answers_json, {})
    answers_map = {}
    if isinstance(state, dict):
        answers_map = state.get("updates", {}) or {}
    if not answers_map:
        answers_map = {}
    for item in answers:
        qid = item.get("question_id")
        if not qid:
            continue
        answers_map[qid] = item.get("answer")

    base_ontology = _safe_json_loads(base_version.ontology_json, {})
    enriched_ontology = await _apply_answers_to_ontology(base_ontology, answers_map)
    refined_after_enrichment = await _llm_refine_ontology(
        ontology=enriched_ontology,
        db_schema_json=db_connection.db_schema,
        db_type=db_connection.db_type,
    )
    enriched_ontology = _merge_refined_with_canonical_mappings(enriched_ontology, refined_after_enrichment)
    enriched_graph = _ontology_to_graph(enriched_ontology)

    latest = _get_latest_ontology_version(db, connection_id)
    next_version = 1 if not latest else latest.version_number + 1

    user_id = token_payload.get("sub") if token_payload else None

    new_version = OntologyVersionModel(
        id=uuid4(),
        datasource_connection_id=connection_id,
        version_number=next_version,
        version_label=f"enriched_v{next_version}",
        status="published",
        is_base=False,
        ontology_json=json.dumps(enriched_ontology),
        ontology_ttl=_ontology_to_ttl(enriched_ontology),
        graph_json=json.dumps(enriched_graph),
        created_by=UUID(user_id) if user_id else None,
    )

    session.answers_json = json.dumps({"chat_history": state.get("chat_history", []), "updates": answers_map})
    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)

    db.add(new_version)
    db.commit()
    db.refresh(new_version)

    return {
        "ontology_version_id": str(new_version.id),
        "version_label": new_version.version_label,
        "status": new_version.status,
        "is_base": False,
        "graph": enriched_graph,
        "ontology": enriched_ontology,
    }
