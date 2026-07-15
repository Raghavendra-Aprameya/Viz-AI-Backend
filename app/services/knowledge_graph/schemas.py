"""
Pydantic schemas for PDF/DOCX knowledge graph APIs.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class KnowledgeGraphUploadResponse(BaseModel):
    graph_id: UUID


class KnowledgeGraphNode(BaseModel):
    id: str
    label: str
    type: str = "Other"


class KnowledgeGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str


class KnowledgeGraphStats(BaseModel):
    node_count: int = 0
    edge_count: int = 0
    page_count: int = 0


class KnowledgeGraphPayload(BaseModel):
    nodes: List[KnowledgeGraphNode] = Field(default_factory=list)
    edges: List[KnowledgeGraphEdge] = Field(default_factory=list)
    stats: KnowledgeGraphStats = Field(default_factory=KnowledgeGraphStats)


class KnowledgeGraphDetailResponse(BaseModel):
    graph_id: UUID
    filename: str
    page_count: int
    created_at: Optional[datetime] = None
    graph: Dict[str, Any]


class KnowledgeGraphListItem(BaseModel):
    graph_id: UUID
    filename: str
    page_count: int
    created_at: Optional[datetime] = None


class KnowledgeGraphListResponse(BaseModel):
    items: List[KnowledgeGraphListItem] = Field(default_factory=list)


class KnowledgeGraphDeleteResponse(BaseModel):
    message: str
