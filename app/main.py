from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.middleware.response_time import ResponseTimeMiddleware

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

# For SQLAlchemy session, if used elsewhere
# Create a single FastAPI app instance
app = FastAPI()

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

app.add_middleware(ResponseTimeMiddleware)
