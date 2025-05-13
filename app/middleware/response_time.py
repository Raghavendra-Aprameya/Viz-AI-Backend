"""
Middleware to measure and record API response times in FastAPI.

This module defines a middleware that captures the processing time for each request,
stores or updates the response time in the database, and attaches the time to a response header.
"""

import time
import uuid
import logging
from datetime import datetime
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import get_db
from app.models.schema_models import ResponseTimeModel

logger = logging.getLogger(__name__)


class ResponseTimeMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track and log API response times and store metrics in the database.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        path = request.url.path

        response.headers["X-Response-Time"] = f"{process_time:.4f} seconds"

        try:
            db_gen = get_db()
            db = next(db_gen)
            try:
                record = (
                    db.query(ResponseTimeModel)
                    .filter(ResponseTimeModel.url == path)
                    .first()
                )

                if record:
                    total_time = record.avg_process_time * record.request_count
                    new_avg = (total_time + process_time) / (record.request_count + 1)

                    record.avg_process_time = new_avg
                    record.last_process_time = process_time
                    record.request_count += 1
                    record.updated_at = datetime.utcnow()
                else:
                    new_record = ResponseTimeModel(
                        id=uuid.uuid4(),
                        url=path,
                        avg_process_time=process_time,
                        last_process_time=process_time,
                        request_count=1,
                    )
                    db.add(new_record)

                db.commit()
                logger.info("Request URL: %s, Processing Time: %.4f seconds", path, process_time)

            except SQLAlchemyError as db_err:
                db.rollback()
                logger.exception("Database operation failed for %s: %s", path, db_err)
            finally:
                db.close()

        except StopIteration:
            logger.exception("Failed to get DB session generator.")

        return response
