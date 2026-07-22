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
    related_tables: Optional[List[str]] = []

class BusinessMetricsResponse(BaseModel):
    metrics: List[BusinessMetric]

class RelationshipSummary(BaseModel):
    source: str
    target: str
    source_column: str
    target_column: str
    label: Optional[str] = None
    
class RelationshipListResponse(BaseModel):
    relationships: List[RelationshipSummary]

