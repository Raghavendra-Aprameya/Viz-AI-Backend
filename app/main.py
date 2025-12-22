from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request,WebSocket
from fastapi.middleware.cors import CORSMiddleware

from app.middleware.response_time import ResponseTimeMiddleware
from app.middleware.request_logging import RequestResponseLoggingMiddleware

# Import routers and constants
from app.routes.auth import auth_router
from app.routes.backend import backend_router
from app.routes.llm import llm_router
from app.utils.constants import (
    ALLOWED_ORIGINS,
    ALLOWED_CREDENTIALS,
    ALLOWED_METHODS,
    ALLOWED_HEADERS,
)
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown events.

    Handles:
    - Graceful shutdown of external database engine pool
    """
    # Startup
    logger.info("Starting VizAI Backend...")
    yield
    # Shutdown
    logger.info("Shutting down VizAI Backend...")
    from app.core.db import external_engine_manager
    external_engine_manager.dispose_all()
    logger.info("All external engines disposed successfully")


# For SQLAlchemy session, if used elsewhere
# Create a single FastAPI app instance with lifespan
app = FastAPI(lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOWED_CREDENTIALS,
    allow_methods=ALLOWED_METHODS,
    allow_headers=ALLOWED_HEADERS,
)


# Include routers for your endpoints
app.include_router(auth_router)  # Include auth-related endpoints
app.include_router(backend_router)
app.include_router(llm_router)  # Include backend-related endpoints

app.add_middleware(RequestResponseLoggingMiddleware)
app.add_middleware(ResponseTimeMiddleware)


@app.get("/")
async def root():
    return {"message": "hello"}

@app.websocket("/ws/test")
async def ws_test(ws: WebSocket):
    await ws.accept()
    await ws.send_text("Hello WS!")
    await ws.close()

