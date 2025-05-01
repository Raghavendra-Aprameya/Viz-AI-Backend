from uuid import UUID

from fastapi import APIRouter, Depends, Path, Body
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas import AddSpreadsheetRequest
from app.services.spreadsheet import (
    get_spreadsheet_data,
    generate_chart_data,
    add_spreadsheet_datasource_service,
)
from app.utils.token_parser import get_current_user

llm_router = APIRouter(prefix="/api/v1/llm", tags=["llm"])


@llm_router.get("/spreadsheet")
def get_spreadsheet():
    """
    Endpoint to retrieve spreadsheet data.
    """
    return get_spreadsheet_data()


@llm_router.get("/generate_charts")
def generate_charts():
    """
    Endpoint to generate chart data from spreadsheet.
    """
    return generate_chart_data()


@llm_router.post("/project/{project_id}/add-spreadsheet-datasource")
def add_spreadsheet_datasource(
    project_id: UUID = Path(..., description="Project ID to add spreadsheet datasource to"),
    data: AddSpreadsheetRequest = Body(...),
    db: Session = Depends(get_db),
    token_payload: dict = Depends(get_current_user),
):
    """
    Endpoint to add a spreadsheet as a datasource for a specific project.

    Args:
        project_id (UUID): ID of the project.
        data (AddSpreadsheetRequest): Spreadsheet configuration and content.
        db (Session): Database session.
        token_payload (dict): Authenticated user token payload.

    Returns:
        dict: Success message or created datasource details.
    """
    return add_spreadsheet_datasource_service(project_id, data, db, token_payload)
