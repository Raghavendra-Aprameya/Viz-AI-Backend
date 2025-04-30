import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable
from fastapi import Request
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.db import get_db
from app.models.schema_models import ResponseTimeModel

class ResponseTimeMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware to calculate response time.
    
    This middleware measures the time difference between when a request is received
    and when the response is sent, adding this information to response headers and
    storing the data in the database for performance tracking.
    """
    
    async def dispatch(self, request: Request, call_next: Callable):
        # Record start time
        start_time = time.time()
        
        # Process the request
        response = await call_next(request)
        
        # Calculate processing time
        process_time = time.time() - start_time
        
        # Get the request path
        path = request.url.path
        
        # Store the processing time in the database
        try:
            # Get database session
            db = next(get_db())
            try:
                # Check if there's an existing record for this path
                existing_record = db.query(ResponseTimeModel).filter(
                    ResponseTimeModel.url == path
                ).first()
                
                if existing_record:
                    # Update the average time
                    new_avg = ((existing_record.avg_process_time * existing_record.request_count) + process_time) / (existing_record.request_count + 1)
                    existing_record.avg_process_time = new_avg
                    existing_record.request_count += 1
                    existing_record.last_process_time = process_time
                    existing_record.updated_at = datetime.utcnow()
                else:
                    # Create new record with UUID
                    new_record = ResponseTimeModel(
                        id=uuid.uuid4(),  # Generate a UUID for the new record
                        url=path,
                        avg_process_time=process_time,
                        last_process_time=process_time,
                        request_count=1
                    )
                    db.add(new_record)
                
                db.commit()
                print(f"Request URL: {path}, Processing Time: {process_time:.4f} seconds")
            except Exception as e:
                db.rollback()
                print(f"Failed to store response time: {e}")
            finally:
                db.close()
        except Exception as e:
            print(f"Database error in middleware: {e}")
        
        # Add custom header with processing time in milliseconds
        response.headers["X-Response-Time"] = f"{process_time:.4f} seconds"
        
        return response