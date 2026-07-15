"""Local filesystem helpers for knowledge-graph document uploads."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID


def get_upload_root() -> Path:
    root = os.getenv("KG_UPLOAD_DIR", "uploads/knowledge_graphs")
    path = Path(root)
    if not path.is_absolute():
        # Resolve relative to Viz-AI-Backend project root (cwd when running uvicorn)
        path = Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_file_path(user_id: UUID, graph_id: UUID, extension: str) -> Path:
    ext = extension if extension.startswith(".") else f".{extension}"
    user_dir = get_upload_root() / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / f"{graph_id}{ext}"


def save_upload_bytes(
    user_id: UUID,
    graph_id: UUID,
    content: bytes,
    extension: str,
) -> str:
    path = build_file_path(user_id, graph_id, extension)
    path.write_bytes(content)
    return str(path)


def delete_upload(file_path: str | None) -> None:
    if not file_path:
        return
    path = Path(file_path)
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass
