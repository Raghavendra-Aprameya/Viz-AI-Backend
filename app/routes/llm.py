from fastapi import APIRouter, status, Response, Depends, Request, Path, HTTPException, Body
from uuid import UUID
from sqlalchemy.orm import Session
from app.services.spreadsheet import get_spreadsheet_data, generate_chart_data, add_spreadsheet_datasource_service
from app.core.db import get_db
from app.utils.token_parser import get_current_user
from app.schemas import AddSpreadsheetRequest
llm_router = APIRouter(prefix="/api/v1/llm", tags=["llm"])

@llm_router.get("/spreadsheet")
def get_spreadsheet():

    """
    Endpoint to get spreadsheet data.
    """
    return get_spreadsheet_data()
@llm_router.get("/generate_charts")
def generate_charts():
    return generate_chart_data()



@llm_router.post("/project/{project_id}/add-spreadsheet-datasource")
def add_spreadsheet_datasource(
    project_id: UUID = Path(..., description="Project ID to add spreadsheet datasource to"),
    data: AddSpreadsheetRequest = Body(...),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user)
):
    return add_spreadsheet_datasource_service(project_id, data, db, token_payload)


# TODO: add router to get latest date from DB for date range enforcement