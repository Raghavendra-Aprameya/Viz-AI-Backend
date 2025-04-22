"""
This module contains the FastAPI application instance and defines the routes for the API.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# from routes import router

from app.routes.auth import auth_router
from app.routes.backend import backend_router
from app.utils.constants import ALLOWED_ORIGINS, ALLOWED_CREDENTIALS,ALLOWED_METHODS,ALLOWED_HEADERS
# from database import engine, Base

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOWED_CREDENTIALS,
    allow_methods=ALLOWED_METHODS,
    allow_headers=ALLOWED_HEADERS,
)

app.include_router(auth_router)
app.include_router(backend_router)

# @app.get("/")
# def read_root():
#     return {"message": "Welcome to the Database Connection Service API"}
