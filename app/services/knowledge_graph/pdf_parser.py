"""PDF text extraction and chunking for knowledge-graph generation."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

import fitz  # PyMuPDF
from fastapi import HTTPException, status


def get_max_pages() -> int:
    return int(os.getenv("KG_MAX_PAGES", "20"))


def get_max_file_mb() -> int:
    return int(os.getenv("KG_MAX_FILE_MB", "20"))


def get_chunk_page_size() -> int:
    return int(os.getenv("KG_CHUNK_PAGES", "5"))


def validate_pdf_upload(filename: str | None, content: bytes) -> None:
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )
    name = (filename or "").lower()
    if not name.endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported",
        )
    max_bytes = get_max_file_mb() * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PDF exceeds maximum size of {get_max_file_mb()} MB",
        )


def extract_pages_and_chunks(content: bytes) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Returns (page_count, chunks) where each chunk is:
    { page_start, page_end, text }
    """
    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or unreadable PDF: {exc}",
        ) from exc

    try:
        page_count = doc.page_count
        max_pages = get_max_pages()
        if page_count < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PDF has no pages",
            )
        if page_count > max_pages:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"PDF has {page_count} pages; maximum allowed is {max_pages}",
            )

        page_texts: List[str] = []
        for i in range(page_count):
            page_texts.append(doc.load_page(i).get_text("text") or "")

        chunk_size = max(1, get_chunk_page_size())
        chunks: List[Dict[str, Any]] = []
        for start_idx in range(0, page_count, chunk_size):
            end_idx = min(start_idx + chunk_size, page_count)
            text = "\n\n".join(page_texts[start_idx:end_idx]).strip()
            chunks.append(
                {
                    "page_start": start_idx + 1,
                    "page_end": end_idx,
                    "text": text,
                }
            )
        return page_count, chunks
    finally:
        doc.close()
