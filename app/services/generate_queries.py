from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import text,create_engine
from fastapi import HTTPException, status, Depends
from uuid import UUID
from typing import Any
import httpx
from app.models.schema_models import ChartModel, DashboardChartsModel, DatabaseConnectionModel
from app.schemas import QueryRequest
from app.utils.token_parser import  get_current_user
from app.utils.crypt import decrypt_string


LLM_SERVICE_URL = "http://192.168.0.39:8001/queries/"
# celery -A app.utils.tasks.celery_app worker --loglevel=info
# celery -A app.utils.tasks.celery_app worker --loglevel=info
async def post_to_llm(url: str, payload: dict) -> Any:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload) 
            response.raise_for_status()
            return response.json() 
    except httpx.RequestError as e:
        raise Exception(f"Error communicating with LLM service at {url}: {str(e)}")
    except httpx.HTTPStatusError as e:
        raise Exception(f"LLM service error: {str(e.response.status_code)} - {str(e.response.text)}")


async def generate_and_store_charts(
    db: Session,
    datasource_connection_id: UUID,
    project_id: UUID,
    query_request: QueryRequest,
    token_payload: dict = Depends(get_current_user)
):
    db_conn = db.query(DatabaseConnectionModel).filter_by(id=datasource_connection_id,
                                                        project_id=project_id).first()
    if not db_conn:
        raise HTTPException(status_code=404, detail="No database connection found for this project or db connection not found")
    
    user_id_str = token_payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    
    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid UUID format in token")
    print(query_request.db_type)
    llm_payload = {
        "db_schema": db_conn.db_schema,
        "db_type": query_request.db_type,
        "role": query_request.role,
        "domain": query_request.domain,
        "min_date": query_request.min_date,
        "max_date": query_request.max_date,
        "api_key": query_request.api_key,
    }

    llm_response = await post_to_llm(LLM_SERVICE_URL, llm_payload)
    queries = llm_response.get("queries", [])

    chart_models = []
    for q in queries:
        chart = ChartModel(
            title=q["explanation"][:80],
            query=q["query"],
            report=q["explanation"],
            type=q["chart_type"],
            relevance=q["relevance"],
            is_time_based=q["is_time_based"],
            chart_type=q["chart_type"],
            is_user_generated=False,
            created_by=user_id
        )
        db.add(chart)
        db.flush()

        # assoc = DashboardChartsModel(
        #     chart_id=chart.id,
        #     dashboard_id=dashboard_id,
        # )
        # db.add(assoc)
        chart_models.append(chart)

    db.commit()
    return chart_models

def execute_external_query(query_id:UUID,
                            db:Session,
                            datasource_connection_id:UUID,
                            token_payload: dict = Depends(get_current_user),
                            ):
    """
    Executes a SQL query on the external database.
    """
    user_id_str = token_payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    
    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid UUID format in token")
    
    generated_query = db.query(ChartModel).filter(ChartModel.id == query_id).first()
    if not generated_query:
        raise HTTPException(status_code=404, detail="Query not found")
    query = generated_query.query
    
    datasource_connection_id  = db.query(DatabaseConnectionModel).filter_by(id = datasource_connection_id ).first()
    if not datasource_connection_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Datasource Connection ID dosent Exist")
    
    decrypt_conn_string = decrypt_string(datasource_connection_id.db_connection_string)
    engine = create_engine(decrypt_conn_string)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        print(query)
        result = session.execute(text(query))
        data = result.fetchall()  
        print(data)
        # Fetch all results
        response = [dict(row._mapping) for row in data]  # Convert result to dictionary
        transformed_data =  transform_data_dynamic(response)
        print(transformed_data)
        response =  {
        "result": transformed_data["data"],
        "x_axis": transformed_data["x_axis"],
        "y_axis": transformed_data["y_axis"],
        "id": str(generated_query.id),
        "chartType": generated_query.chart_type,
        "report": generated_query.report
        }
        print(response)
        return response
    except Exception as e:
        return {"error": str(e)}
    finally:
        session.close()  # Close session after use
        engine.dispose() 



def transform_data_dynamic(data):
    """
    Transforms an array of dictionaries into the required format by dynamically detecting fields.
    Also returns the detected x-axis and y-axis labels.

    :param data: List of dictionaries with unknown key names
    :return: Dictionary containing transformed data and axis labels
    """
    if not data:
        return {"data": [], "x_axis": None, "y_axis": None}

    keys = list(data[0].keys())

    if len(keys) < 2:
        raise ValueError("Data must contain at least two fields (one for label and one for value).")

    x_axis = keys[0]  # First key for x-axis
    y_axis = keys[1]  # Second key for y-axis

    transformed_data = [{"label": str(item[x_axis]), "value": item[y_axis]} for item in data]

    return {"data": transformed_data, "x_axis": x_axis, "y_axis": y_axis}
