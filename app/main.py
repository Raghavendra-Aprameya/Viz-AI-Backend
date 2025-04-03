from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import router
from app.routes.db_connection import db_router
# from database import engine, Base

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(db_router)

# @app.get("/")
# def read_root():
#     return {"message": "Welcome to the Database Connection Service API"}
