"""HTTP client for the LLM knowledge-graph extract service."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


def get_extract_url() -> str:
    return os.getenv(
        "KG_EXTRACT_URL",
        "http://localhost:8001/api/knowledge-graph/extract",
    )


def get_extract_timeout() -> float:
    return float(os.getenv("KG_EXTRACT_TIMEOUT", "600"))


async def extract_knowledge_graph(
    *,
    filename: str,
    page_count: int,
    chunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    url = get_extract_url()
    timeout = get_extract_timeout()
    payload = {
        "filename": filename,
        "page_count": page_count,
        "chunks": chunks,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or "nodes" not in data or "edges" not in data:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="LLM service returned an invalid knowledge graph payload",
                )
            return data
    except httpx.TimeoutException as exc:
        logger.error("KG extract timed out calling %s", url)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Knowledge graph extraction timed out",
        ) from exc
    except httpx.HTTPStatusError as exc:
        detail: Optional[str] = None
        try:
            detail = exc.response.json().get("detail")
        except Exception:
            detail = exc.response.text
        logger.error("KG extract HTTP error: %s | detail=%s", exc, detail)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail or "Knowledge graph extraction failed in LLM service",
        ) from exc
    except httpx.RequestError as exc:
        logger.error("KG extract request error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not reach knowledge graph LLM service: {exc}",
        ) from exc
