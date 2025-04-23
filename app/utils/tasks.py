
from time import sleep
from turtle import back
from celery import Celery
from app.services.generate_queries import generate_and_store_charts
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


celery_app = Celery('tasks', broker='redis://localhost:6379/0',backend='redis://localhost:6379/0')

# @app.task
# def generate_charts_asynchronously():
#     #write code to generate charts
#     chart_models =  generate_and_store_charts(
#         db=db,
#         datasource_connection_id=datasource_connection_id,
#         project_id=project_id,
#         query_request=query_request,
#         token_payload=token_payload
#     )

#     # Serialize chart data for Redis storage
#     charts_serialized = [{
#         "id": str(chart.id),
#         "title": chart.title,
#         "chart_type": chart.chart_type,
#         "created_at": chart.created_at.isoformat() if hasattr(chart, 'created_at') else None
#     } for chart in chart_models]
    
#     # Store current charts in Redis
#     r.set(f"charts:current:{user_id}", json.dumps(charts_serialized))
    
#     # Start background task to generate next batch of charts
#     generate_charts_asynchronously.delay(user_id, str(datasource_connection_id), str(project_id))

#     return chart_models
@celery_app.task
def generate_charts_asynchronously(
    user_id,
    datasource_connection_id=None,
    project_id=None,
    query_request=None
):
    """
    Celery task to generate charts asynchronously and store them in Redis
    for quick access on the next user request.
    """
    try:
        # Create a new database session for this background task
        db = SessionLocal()
        
        # Convert string IDs back to UUID objects if provided
        ds_conn_id = UUID(datasource_connection_id) if datasource_connection_id else None
        proj_id = UUID(project_id) if project_id else None
        
        # Get user token payload from somewhere (depends on your auth system)
        # This is a placeholder - you'll need to implement a way to get valid token payload
        token_payload = {"user_id": user_id}
        
        # Generate the charts
        chart_models = generate_and_store_charts(
            db=db,
            datasource_connection_id=ds_conn_id,
            project_id=proj_id,
            query_request=query_request,
            token_payload=token_payload
        )

        # Serialize chart data for Redis storage
        charts_serialized = [{
            "id": str(chart.id),
            "title": chart.title,
            "chart_type": chart.chart_type,
            "created_at": chart.created_at.isoformat() if hasattr(chart, 'created_at') else None,
            "data": chart.data if hasattr(chart, 'data') else None,
            # Add other relevant chart fields here
        } for chart in chart_models]
        
        # Store next batch of charts in Redis with expiration (e.g., 1 hour)
        redis_key = f"charts:next:{user_id}"
        r.set(redis_key, json.dumps(charts_serialized), ex=3600)
        
        logger.info(f"Successfully generated next batch of charts for user {user_id}")
        
        # Clean up
        db.close()
        
        return {
            "status": "success",
            "message": f"Generated {len(charts_serialized)} charts for next batch",
            "user_id": user_id
        }
        
    except Exception as e:
        logger.error(f"Error in generate_charts_asynchronously task: {str(e)}")
        # If db session was created, ensure it's closed even on error
        if 'db' in locals():
            db.close()
        
        return {
            "status": "error",
            "message": f"Failed to generate next batch of charts: {str(e)}",
            "user_id": user_id
        }