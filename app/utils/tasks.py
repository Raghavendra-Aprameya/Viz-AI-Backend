from fastapi import HTTPException, status, Request, Depends
import jwt
from app.core.settings import settings

async def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header")
    
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

# Keep the original parse_token for backward compatibility
def parse_token(request: Request):
    return get_current_user(request)# from time import sleep
# from turtle import back
# from celery import Celery
# from app.services.generate_queries import generate_and_store_charts
# import logging


# logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.INFO)


# celery_app = Celery('tasks', broker='redis://localhost:6379/0',backend='redis://localhost:6379/0')

# # @app.task
# # def generate_charts_asynchronously():
# #     #write code to generate charts
# #     chart_models =  generate_and_store_charts(
# #         db=db,
# #         datasource_connection_id=datasource_connection_id,
# #         project_id=project_id,
# #         query_request=query_request,
# #         token_payload=token_payload
# #     )

# #     # Serialize chart data for Redis storage
# #     charts_serialized = [{
# #         "id": str(chart.id),
# #         "title": chart.title,
# #         "chart_type": chart.chart_type,
# #         "created_at": chart.created_at.isoformat() if hasattr(chart, 'created_at') else None
# #     } for chart in chart_models]

# #     # Store current charts in Redis
# #     r.set(f"charts:current:{user_id}", json.dumps(charts_serialized))

# #     # Start background task to generate next batch of charts
# #     generate_charts_asynchronously.delay(user_id, str(datasource_connection_id), str(project_id))

# #     return chart_models
# @celery_app.task
# def generate_charts_asynchronously(
#     user_id,
#     datasource_connection_id=None,
#     project_id=None,
#     query_request=None
# ):
#     """
#     Celery task to generate charts asynchronously and store them in Redis
#     for quick access on the next user request.
#     """
#     try:
#         # Create a new database session for this background task
#         db =

#         # Convert string IDs back to UUID objects if provided
#         ds_conn_id = UUID(datasource_connection_id) if datasource_connection_id else None
#         proj_id = UUID(project_id) if project_id else None

#         # Get user token payload from somewhere (depends on your auth system)
#         # This is a placeholder - you'll need to implement a way to get valid token payload
#         token_payload = {"user_id": user_id}

#         # Generate the charts
#         chart_models = generate_and_store_charts(
#             db=db,
#             datasource_connection_id=ds_conn_id,
#             project_id=proj_id,
#             query_request=query_request,
#             token_payload=token_payload
#         )

#         # Serialize chart data for Redis storage
#         charts_serialized = [{
#             "id": str(chart.id),
#             "title": chart.title,
#             "chart_type": chart.chart_type,
#             "created_at": chart.created_at.isoformat() if hasattr(chart, 'created_at') else None,
#             "data": chart.data if hasattr(chart, 'data') else None,
#             # Add other relevant chart fields here
#         } for chart in chart_models]

#         # Store next batch of charts in Redis with expiration (e.g., 1 hour)
#         redis_key = f"charts:next:{user_id}"
#         r.set(redis_key, json.dumps(charts_serialized), ex=3600)

#         logger.info(f"Successfully generated next batch of charts for user {user_id}")

#         # Clean up
#         db.close()

#         return {
#             "status": "success",
#             "message": f"Generated {len(charts_serialized)} charts for next batch",
#             "user_id": user_id
#         }

#     except Exception as e:
#         logger.error(f"Error in generate_charts_asynchronously task: {str(e)}")
#         # If db session was created, ensure it's closed even on error
#         if 'db' in locals():
#             db.close()

#         return {
#             "status": "error",
#             "message": f"Failed to generate next batch of charts: {str(e)}",
#             "user_id": user_id
#         }import json
import json
import logging
from uuid import UUID

from celery import Celery
import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services.generate_queries import generate_and_store_charts
from app.core.settings import settings
from app.schemas import QueryRequest  # Import the QueryRequest schema

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Celery app config with properly configured serializer
celery_app = Celery(
    "tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0"
)

# Configure Celery to use 'solo' instead of 'fork' on macOS
celery_app.conf.update(
    worker_pool="solo",  # Use solo pool instead of prefork on macOS
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
)

# Redis client
r = redis.Redis(host="localhost", port=6379, db=0)

# Create engine outside of task to avoid recreation
engine = create_engine(
    url=settings.DB_URI,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=5,
    max_overflow=10,
)
TaskSessionLocal = sessionmaker(bind=engine, autoflush=False)


# Function to run async code in synchronous context
def run_async(async_func, *args, **kwargs):
    import asyncio

    # Create a new event loop for this function call
    loop = asyncio.new_event_loop()
    try:
        # Run the async function and return the result
        return loop.run_until_complete(async_func(*args, **kwargs))
    finally:
        # Always close the loop to free up resources
        loop.close()


@celery_app.task
def generate_charts_asynchronously(
    user_id, datasource_connection_id=None, project_id=None, query_request=None
):
    """
    Celery task to generate charts asynchronously and store them in Redis
    for quick access on the next user request.
    """
    try:
        # Create a database session
        db = TaskSessionLocal()

        # Convert string IDs to UUID if provided
        ds_conn_id = (
            UUID(datasource_connection_id) if datasource_connection_id else None
        )
        proj_id = UUID(project_id) if project_id else None

        # Token payload with user ID
        token_payload = {"sub": user_id}

        logger.info(f"Starting chart generation for user {user_id}")

        # Convert the dictionary back to a QueryRequest object
        # This is needed because we pass query_request.dict() when calling the task
        if query_request is not None:
            logger.info(f"Converting dict to QueryRequest: {query_request}")
            query_request_obj = QueryRequest(**query_request)
        else:
            logger.warning(f"No query_request provided for user {user_id}")
            query_request_obj = None

        # Use our helper function to run the async function
        chart_models = run_async(
            generate_and_store_charts,
            db=db,
            datasource_connection_id=ds_conn_id,
            project_id=proj_id,
            query_request=query_request_obj,
            token_payload=token_payload,
        )

        # Serialize for Redis
        charts_serialized = [
            {
                "id": str(chart.id),
                "title": chart.title,
                "chart_type": chart.chart_type,
                "created_at": (
                    chart.created_at.isoformat()
                    if hasattr(chart, "created_at")
                    else None
                ),
                "data": getattr(chart, "data", None),
            }
            for chart in chart_models
        ]

        # Store in Redis
        redis_key = f"charts:next:{user_id}"
        r.set(redis_key, json.dumps(charts_serialized), ex=3600)

        logger.info(f"✅ Successfully generated charts for user {user_id}")
        db.close()

        return {
            "status": "success",
            "message": f"Generated {len(charts_serialized)} charts for next batch",
            "user_id": user_id,
        }

    except Exception as e:
        logger.error(f"❌ Error in generate_charts_asynchronously task: {str(e)}")
        if "db" in locals():
            db.close()
        return {
            "status": "error",
            "message": f"Failed to generate next batch of charts: {str(e)}",
            "user_id": user_id,
        }
