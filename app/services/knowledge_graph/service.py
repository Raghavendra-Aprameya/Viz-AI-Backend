"""
Knowledge graph business logic: sync PDF upload, get, list, delete.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.knowledge_graph_models import DocumentKnowledgeGraphModel
from app.services.knowledge_graph.schemas import (
    KnowledgeGraphDeleteResponse,
    KnowledgeGraphDetailResponse,
    KnowledgeGraphListItem,
    KnowledgeGraphListResponse,
    KnowledgeGraphUploadResponse,
)
from app.services.knowledge_graph import llm_client, pdf_parser, storage
from app.utils.token_parser import get_current_user

logger = logging.getLogger(__name__)


def _user_id_from_token(token_payload: dict) -> UUID:
    sub = token_payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    try:
        return UUID(str(sub))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user id in token",
        ) from exc


def _owned_graph_or_404(
    db: Session,
    graph_id: UUID,
    user_id: UUID,
) -> DocumentKnowledgeGraphModel:
    row = (
        db.query(DocumentKnowledgeGraphModel)
        .filter(
            DocumentKnowledgeGraphModel.id == graph_id,
            DocumentKnowledgeGraphModel.user_id == user_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge graph not found",
        )
    return row


async def upload_knowledge_graph_pdf(
    file: UploadFile,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
) -> KnowledgeGraphUploadResponse:
    user_id = _user_id_from_token(token_payload)
    content = await file.read()
    pdf_parser.validate_pdf_upload(file.filename, content)

    graph_id = uuid4()
    filename = file.filename or f"{graph_id}.pdf"
    file_path: str | None = None

    try:
        page_count, chunks = pdf_parser.extract_pages_and_chunks(content)
        file_path = storage.save_pdf_bytes(user_id, graph_id, content)

        graph_payload: Dict[str, Any] = await llm_client.extract_knowledge_graph(
            filename=filename,
            page_count=page_count,
            chunks=chunks,
        )

        row = DocumentKnowledgeGraphModel(
            id=graph_id,
            user_id=user_id,
            filename=filename,
            file_path=file_path,
            page_count=page_count,
            graph_json=json.dumps(graph_payload),
        )
        db.add(row)
        db.commit()
        logger.info(
            "Knowledge graph created | graph_id=%s user_id=%s pages=%s",
            graph_id,
            user_id,
            page_count,
        )
        return KnowledgeGraphUploadResponse(graph_id=graph_id)
    except HTTPException:
        storage.delete_pdf(file_path)
        db.rollback()
        raise
    except Exception as exc:
        storage.delete_pdf(file_path)
        db.rollback()
        logger.error("Knowledge graph upload failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create knowledge graph: {exc}",
        ) from exc


async def get_knowledge_graph(
    graph_id: UUID,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
) -> KnowledgeGraphDetailResponse:
    user_id = _user_id_from_token(token_payload)
    row = _owned_graph_or_404(db, graph_id, user_id)
    try:
        graph = json.loads(row.graph_json) if row.graph_json else {"nodes": [], "edges": [], "stats": {}}
    except json.JSONDecodeError:
        graph = {"nodes": [], "edges": [], "stats": {}}
    return KnowledgeGraphDetailResponse(
        graph_id=row.id,
        filename=row.filename,
        page_count=row.page_count,
        created_at=row.created_at,
        graph=graph,
    )


async def list_knowledge_graphs(
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
) -> KnowledgeGraphListResponse:
    user_id = _user_id_from_token(token_payload)
    rows = (
        db.query(DocumentKnowledgeGraphModel)
        .filter(DocumentKnowledgeGraphModel.user_id == user_id)
        .order_by(DocumentKnowledgeGraphModel.created_at.desc())
        .all()
    )
    items = [
        KnowledgeGraphListItem(
            graph_id=row.id,
            filename=row.filename,
            page_count=row.page_count,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return KnowledgeGraphListResponse(items=items)


async def delete_knowledge_graph(
    graph_id: UUID,
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
) -> KnowledgeGraphDeleteResponse:
    user_id = _user_id_from_token(token_payload)
    row = _owned_graph_or_404(db, graph_id, user_id)
    file_path = row.file_path
    db.delete(row)
    db.commit()
    storage.delete_pdf(file_path)
    return KnowledgeGraphDeleteResponse(message="Knowledge graph deleted")
