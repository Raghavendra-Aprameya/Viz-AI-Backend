from pydantic import BaseModel, Field
from typing import List, Optional

class ColumnOntologyEdit(BaseModel):
    business_definition: str
    semantic_type: str
    status: str

class TableOntologyEdit(BaseModel):
    description: str
    category: str
    status: str

class OntologySyncResponse(BaseModel):
    message: str

class OntologyCategoryResponse(BaseModel):
    categories: List[str]

class OntologyTableSummary(BaseModel):
    physical_name: str
    category: str
    status: str
    is_ai_generated: bool
    confidence: Optional[float] = None
    description: Optional[str] = None
    business_purpose: Optional[str] = None
    business_concepts: Optional[List[str]] = None
    common_questions: Optional[List[str]] = None
    last_updated: Optional[str] = None
    tags: Optional[List[str]] = None
    column_count: Optional[int] = None

class OntologyTableListResponse(BaseModel):
    tables: List[OntologyTableSummary]

class OntologyColumnSummary(BaseModel):
    physical_name: str
    semantic_type: str
    business_definition: str
    status: str
    confidence: Optional[float] = None

class OntologyColumnListResponse(BaseModel):
    columns: List[OntologyColumnSummary]

class GenerateDescriptionResponse(BaseModel):
    description: Optional[str] = None
    category: Optional[str] = None
    semantic_type: Optional[str] = None
    business_definition: Optional[str] = None
    confidence: Optional[float] = None

class BusinessMetric(BaseModel):
    name: str
    formula: str
    description: Optional[str] = ""
    source: Optional[str] = "Manual"
    status: Optional[str] = "PENDING"

class BusinessMetricsResponse(BaseModel):
    metrics: List[BusinessMetric]

