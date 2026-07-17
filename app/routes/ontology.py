import uuid
import json
import requests
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.schema_models import OntologyVersionModel, DatabaseConnectionModel
from app.ontology_schemas import (
    OntologySyncResponse,
    OntologyCategoryResponse,
    OntologyTableListResponse,
    OntologyTableSummary,
    OntologyColumnListResponse,
    OntologyColumnSummary,
    GenerateDescriptionResponse,
    TableOntologyEdit,
    ColumnOntologyEdit,
    BusinessMetric,
    BusinessMetricsResponse
)
from app.utils.constants import LLM_ONTOLOGY_URL
from sqlalchemy import create_engine, inspect
from app.utils.crypt import decrypt_string

router = APIRouter()

def _get_latest_ontology(db: Session, datasource_id: uuid.UUID) -> OntologyVersionModel:
    ontology = db.query(OntologyVersionModel).filter(
        OntologyVersionModel.datasource_connection_id == datasource_id
    ).order_by(OntologyVersionModel.version_number.desc()).first()
    
    if not ontology:
        raise HTTPException(status_code=404, detail="Ontology not found. Please sync first.")
    
    return ontology

def _fetch_physical_schema(db: Session, datasource_id: uuid.UUID) -> dict:
    conn = db.query(DatabaseConnectionModel).filter(DatabaseConnectionModel.id == datasource_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Database connection not found.")
    
    try:
        decrypted_url = decrypt_string(conn.db_connection_string)
        engine = create_engine(decrypted_url)
        inspector = inspect(engine)
        
        schema = {}
        for table_name in inspector.get_table_names():
            schema[table_name] = inspector.get_columns(table_name)
            
        engine.dispose()
        return schema
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract physical schema: {str(e)}")

def _add_pending_tables(chunk, enriched_tables):
    for t in chunk:
        enriched_tables.append({
            "physical_name": t["name"],
            "category": "Unknown",
            "description": "",
            "status": "PENDING",
            "columns": [
                {
                    "physical_name": c["name"], 
                    "business_definition": "", 
                    "semantic_type": "Unknown", 
                    "status": "PENDING"
                } for c in t["columns"]
            ]
        })

def _sync_ontology_background(datasource_id: uuid.UUID):
    db = next(get_db())
    try:
        # Extract schema
        schema = _fetch_physical_schema(db, datasource_id)
        
        # Build payload for LLM
        tables_payload = []
        for table_name, columns in schema.items():
            cols = []
            for col in columns:
                cols.append({"name": col.get("name"), "type": str(col.get("type"))})
            tables_payload.append({"name": table_name, "columns": cols})
        
        # Call LLM Service in chunks to prevent OpenAI timeouts on large schemas
        chunk_size = 3
        enriched_tables = []
        for i in range(0, len(tables_payload), chunk_size):
            chunk = tables_payload[i:i + chunk_size]
            try:
                response = requests.post(
                    f"{LLM_ONTOLOGY_URL}/enrich-schema", 
                    json={"tables": chunk},
                    timeout=120
                )
                if response.status_code == 200:
                    enriched_tables.extend(response.json().get("tables", []))
                else:
                    print(f"Warning: Chunk {i} failed: {response.text}")
                    _add_pending_tables(chunk, enriched_tables)
            except Exception as e:
                print(f"Warning: Chunk {i} exception: {e}")
                _add_pending_tables(chunk, enriched_tables)
                
        # Determine next version and preserve existing graph schema if any
        latest = db.query(OntologyVersionModel).filter(
            OntologyVersionModel.datasource_connection_id == datasource_id
        ).order_by(OntologyVersionModel.version_number.desc()).first()
        
        next_version = 1 if not latest else latest.version_number + 1
        
        existing_data = {}
        if latest and latest.ontology_json:
            try:
                existing_data = json.loads(latest.ontology_json)
            except Exception:
                pass
                
        existing_data["tables"] = enriched_tables
        if "business_metrics" not in existing_data:
            existing_data["business_metrics"] = []
        
        enriched_data = existing_data
        
        # Insert into DB
        new_ontology = OntologyVersionModel(
            datasource_connection_id=datasource_id,
            version_number=next_version,
            version_label=f"Auto-generated v{next_version}",
            status="draft",
            ontology_json=json.dumps(enriched_data),
            graph_json=json.dumps({"nodes": [], "edges": [], "stats": {}})
        )
        db.add(new_ontology)
        db.commit()
    except Exception as e:
        print(f"Background Sync Error: {str(e)}")
    finally:
        db.close()


@router.post("/datasources/{datasource_id}/sync", response_model=OntologySyncResponse, status_code=202)
def sync_ontology(datasource_id: uuid.UUID, background_tasks: BackgroundTasks):
    background_tasks.add_task(_sync_ontology_background, datasource_id)
    return {"message": "Ontology synchronization started in the background."}

@router.get("/datasources/{datasource_id}/business-metrics", response_model=BusinessMetricsResponse)
def get_business_metrics(datasource_id: uuid.UUID, db: Session = Depends(get_db)):
    ontology = _get_latest_ontology(db, datasource_id)
    data = json.loads(ontology.ontology_json)
    metrics = data.get("business_metrics", [])
    return {"metrics": metrics}

@router.post("/datasources/{datasource_id}/business-metrics", response_model=BusinessMetric)
def add_business_metric(datasource_id: uuid.UUID, payload: BusinessMetric, db: Session = Depends(get_db)):
    latest = _get_latest_ontology(db, datasource_id)
    data = json.loads(latest.ontology_json)
    metrics = data.setdefault("business_metrics", [])
    
    # Check if exists, update or append
    existing = next((m for m in metrics if m.get("name") == payload.name), None)
    if existing:
        existing.update(payload.dict(exclude_unset=True))
        result = existing
    else:
        new_metric = payload.dict()
        metrics.append(new_metric)
        result = new_metric
        
    next_version = latest.version_number + 1
    new_ontology = OntologyVersionModel(
        datasource_connection_id=datasource_id,
        version_number=next_version,
        version_label=f"Metric Added v{next_version}",
        status="draft",
        ontology_json=json.dumps(data),
        graph_json=latest.graph_json
    )
    db.add(new_ontology)
    db.commit()
    db.refresh(new_ontology)
    
    return result


@router.get("/datasources/{datasource_id}/categories", response_model=OntologyCategoryResponse)
def get_categories(datasource_id: uuid.UUID, db: Session = Depends(get_db)):
    ontology = _get_latest_ontology(db, datasource_id)
    data = json.loads(ontology.ontology_json)
    
    categories = set()
    for table in data.get("tables", []):
        if table.get("category"):
            categories.add(table["category"])
            
    return {"categories": sorted(list(categories))}

@router.get("/datasources/{datasource_id}/tables", response_model=OntologyTableListResponse)
def get_tables(datasource_id: uuid.UUID, category: str = None, db: Session = Depends(get_db)):
    ontology = _get_latest_ontology(db, datasource_id)
    data = json.loads(ontology.ontology_json)
    
    tables = []
    for table in data.get("tables", []):
        if category and table.get("category") != category:
            continue
            
        tables.append(OntologyTableSummary(
            physical_name=table.get("physical_name", ""),
            category=table.get("category", "Unknown"),
            status=table.get("status", "PENDING"),
            is_ai_generated=True,
            confidence=table.get("confidence")
        ))
        
    return {"tables": tables}

@router.get("/tables/{table_name}/columns", response_model=OntologyColumnListResponse)
def get_columns(table_name: str, datasource_id: uuid.UUID, db: Session = Depends(get_db)):
    ontology = _get_latest_ontology(db, datasource_id)
    data = json.loads(ontology.ontology_json)
    
    columns = []
    for table in data.get("tables", []):
        if table.get("physical_name") == table_name:
            for col in table.get("columns", []):
                columns.append(OntologyColumnSummary(
                    physical_name=col.get("physical_name", ""),
                    semantic_type=col.get("semantic_type", "Unknown"),
                    business_definition=col.get("business_definition", ""),
                    status=col.get("status", "PENDING"),
                    confidence=col.get("confidence")
                ))
            break
            
    return {"columns": columns}


@router.post("/tables/{table_name}/generate-description", response_model=GenerateDescriptionResponse)
def generate_table_description(table_name: str, datasource_id: uuid.UUID, db: Session = Depends(get_db)):
    ontology = _get_latest_ontology(db, datasource_id)
    data = json.loads(ontology.ontology_json)
    
    target_table = None
    for table in data.get("tables", []):
        if table.get("physical_name") == table_name:
            target_table = table
            break
            
    if not target_table:
        raise HTTPException(status_code=404, detail="Table not found in ontology.")
        
    payload = {
        "physical_name": table_name,
        "columns": [{"name": c.get("physical_name")} for c in target_table.get("columns", [])]
    }
    
    resp = requests.post(f"{LLM_ONTOLOGY_URL}/generate-table-description", json=payload)
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail="LLM generation failed.")
        
    result = resp.json()
    
    target_table["description"] = result.get("description", "")
    target_table["category"] = result.get("category", "")
    if "confidence" in result:
        target_table["confidence"] = result.get("confidence")
    
    ontology.ontology_json = json.dumps(data)
    db.commit()
    
    return result

@router.post("/columns/{table_name}/{column_name}/generate-description", response_model=GenerateDescriptionResponse)
def generate_column_description(table_name: str, column_name: str, datasource_id: uuid.UUID, db: Session = Depends(get_db)):
    ontology = _get_latest_ontology(db, datasource_id)
    data = json.loads(ontology.ontology_json)
    
    target_col = None
    for table in data.get("tables", []):
        if table.get("physical_name") == table_name:
            for col in table.get("columns", []):
                if col.get("physical_name") == column_name:
                    target_col = col
                    break
            break
            
    if not target_col:
        raise HTTPException(status_code=404, detail="Column not found in ontology.")
        
    payload = {
        "table_name": table_name,
        "column_name": column_name
    }
    
    resp = requests.post(f"{LLM_ONTOLOGY_URL}/generate-column-description", json=payload)
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail="LLM generation failed.")
        
    result = resp.json()
    
    target_col["business_definition"] = result.get("business_definition", "")
    target_col["semantic_type"] = result.get("semantic_type", "")
    if "confidence" in result:
        target_col["confidence"] = result.get("confidence")
    
    ontology.ontology_json = json.dumps(data)
    db.commit()
    
    return result


@router.put("/tables/{table_name}")
def update_table(table_name: str, datasource_id: uuid.UUID, edit: TableOntologyEdit, db: Session = Depends(get_db)):
    ontology = _get_latest_ontology(db, datasource_id)
    data = json.loads(ontology.ontology_json)
    
    for table in data.get("tables", []):
        if table.get("physical_name") == table_name:
            table["description"] = edit.description
            table["category"] = edit.category
            table["status"] = edit.status
            break
            
    ontology.ontology_json = json.dumps(data)
    db.commit()
    return {"message": "Table updated."}

@router.put("/columns/{table_name}/{column_name}")
def update_column(table_name: str, column_name: str, datasource_id: uuid.UUID, edit: ColumnOntologyEdit, db: Session = Depends(get_db)):
    ontology = _get_latest_ontology(db, datasource_id)
    data = json.loads(ontology.ontology_json)
    
    for table in data.get("tables", []):
        if table.get("physical_name") == table_name:
            for col in table.get("columns", []):
                if col.get("physical_name") == column_name:
                    col["business_definition"] = edit.business_definition
                    col["semantic_type"] = edit.semantic_type
                    col["status"] = edit.status
                    break
            break
            
    ontology.ontology_json = json.dumps(data)
    db.commit()
    return {"message": "Column updated."}
