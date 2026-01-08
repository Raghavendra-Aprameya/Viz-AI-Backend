"""
This module provides functionality to interact with Google Sheets,
load data into DuckDB, and generate charts based on SQL queries.
It includes functions to fetch data from Google Sheets,
store it in DuckDB, and generate charts using SQL queries.
It also includes a function to add a spreadsheet as a data source
to a project in the database.
"""

import json
import logging
from io import StringIO
from uuid import UUID

import duckdb
import pandas as pd
import requests

logger = logging.getLogger(__name__)
from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Path,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse

from app.models.schema_models import DatabaseConnectionModel, ProjectModel
from app.schemas import AddSpreadsheetRequest


def get_spreadsheet_data():
    # Step 1: Google Spreadsheet ID (replace with your sheet ID)
    sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

    # Step 2: Construct the export URL to fetch CSV data from Google Sheets
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

    # Step 3: Fetch the data from the Google Sheet using requests
    response = requests.get(url)

    # Check if the request was successful
    if response.status_code == 200:
        # Step 4: Load the CSV data into a Pandas DataFrame
        csv_data = StringIO(response.text)
        df = pd.read_csv(csv_data)

        # Step 5: Connect to DuckDB (in-memory or a persistent database)
        con = duckdb.connect()

        # Step 6: Store the data in DuckDB (you can store it in an in-memory database or on disk)
        con.execute("CREATE TABLE IF NOT EXISTS spreadsheet_data AS SELECT * FROM df")

        # Step 7: Extract metadata (column names, data types)
        metadata = con.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'spreadsheet_data'
        """
        ).fetchdf()

        # Convert the metadata to a list of dictionaries
        metadata_list = metadata.to_dict(orient="records")

        # Step 8: Fetch the first 5 rows of the data
        first_5_rows = con.execute("SELECT * FROM spreadsheet_data LIMIT 5").fetchdf()

        # Convert the first 5 rows to a list of dictionaries
        data_list = first_5_rows.to_dict(orient="records")

        # Step 9: Build the response as a dictionary
        response_data = {"metadata": metadata_list, "data": data_list}

        # Step 10: Convert the response data to JSON
        return response_data

    else:
        logger.error(f"Failed to fetch data. HTTP Status code: {response.status_code}")
        return None


# API_KEY = "YOUR_GOOGLE_API_KEY"
# SPREADSHEET_ID = "1ysSALcAXfvajUFe7SRJMDpIfsorikQgJQ_a66Wi4_m8"

# def get_all_sheet_metadata(spreadsheet_id, api_key):
#     # Step 1: Get sheet metadata (sheet names, etc.)
#     metadata_url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}?key={api_key}"
#     metadata_resp = requests.get(metadata_url)
#     metadata = metadata_resp.json()

#     output = {}

#     for sheet in metadata["sheets"]:
#         title = sheet["properties"]["title"]

#         # Step 2: Export each sheet as CSV
#         csv_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq?tqx=out:csv&sheet={title}"
#         csv_resp = requests.get(csv_url)

#         if csv_resp.status_code == 200:
#             csv_data = StringIO(csv_resp.text)
#             df = pd.read_csv(csv_data)

#             # Step 3: Load to DuckDB to extract metadata
#             con = duckdb.connect()
#             con.register("df_view", df)

#             metadata_df = con.execute("""
#                 SELECT column_name, data_type
#                 FROM information_schema.columns
#                 WHERE table_name = 'df_view'
#             """).fetchdf()

#             sample_rows = df.head().to_dict(orient="records")

#             output[title] = {
#                 "metadata": metadata_df.to_dict(orient="records"),
#                 "sample_rows": sample_rows
#             }

#     return output

# # Run it
# result = get_all_sheet_metadata(SPREADSHEET_ID, API_KEY)
# print(result)

# Connect to DuckDB
con = duckdb.connect()

# Your list of LLM-generated queries
queries = [
    {
        "query": 'SELECT "Class Level", COUNT(*) AS StudentCount FROM spreadsheet_data GROUP BY "Class Level"',
        "explanation": "How many students are in each class level?",
        "chart": "Bar",
    },
    {
        "query": "SELECT Major, COUNT(*) AS StudentCount FROM spreadsheet_data GROUP BY Major",
        "explanation": "What is the distribution of majors across all students?",
        "chart": "Pie",
    },
    # Add more queries as needed...
]


def generate_chart_data():
    results = []

    # Ensure table is loaded
    if not load_data_into_duckdb():
        return JSONResponse(
            content={"error": "Failed to load spreadsheet data"}, status_code=500
        )

    for item in queries:
        sql = item["query"]
        explanation = item.get("explanation", "")
        chart_type = item.get("chart", "Bar")

        try:
            df = con.execute(sql).fetchdf()
            results.append(
                {
                    "query": sql,
                    "explanation": explanation,
                    "chart_type": chart_type,
                    "data": df.to_dict(orient="records"),
                }
            )
        except Exception as e:
            results.append({"query": sql, "error": str(e)})

    return JSONResponse(content={"results": results})


def load_data_into_duckdb():
    sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    response = requests.get(url)

    if response.status_code == 200:
        csv_data = StringIO(response.text)
        df = pd.read_csv(csv_data)
        con.execute("CREATE OR REPLACE TABLE spreadsheet_data AS SELECT * FROM df")
        return True
    return False


def add_spreadsheet_datasource_service(project_id, data, db, token_payload):
    try:
        # Validate the project ID and user permissions
        user_id = UUID(token_payload.get("sub"))
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
            )
        project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found or user does not have permission to access it",
            )

        sheet_id = data.sheet_id

        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

        response = requests.get(url)

        if response.status_code == 200:

            csv_data = StringIO(response.text)
            df = pd.read_csv(csv_data)

            con = duckdb.connect()

            con.execute(
                "CREATE TABLE IF NOT EXISTS spreadsheet2_data AS SELECT * FROM df"
            )

            metadata = con.execute(
                """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'spreadsheet2_data'
        """
            ).fetchdf()

            metadata_list = metadata.to_dict(orient="records")

            first_20_rows = con.execute(
                "SELECT * FROM spreadsheet2_data LIMIT 5"
            ).fetchdf()

            data_list = first_20_rows.to_dict(orient="records")

            response_data = {"metadata": metadata_list, "data": data_list}

            db_schema_json = json.dumps(response_data)

            new_data = DatabaseConnectionModel(
                project_id=project_id,
                connection_name=data.connection_name,
                db_type="spreadsheet",
                db_schema=db_schema_json,
                db_connection_string=url,
                consent_given=True,
            )
            db.add(new_data)
            db.commit()
            db.refresh(new_data)
            return new_data

        else:
            logger.error(f"Failed to fetch data. HTTP Status code: {response.status_code}")
            return None
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e
