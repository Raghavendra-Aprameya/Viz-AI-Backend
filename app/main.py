from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# from routes import router

from app.routes.auth import auth_router
from app.routes.backend import backend_router
# from database import engine, Base

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth_router)
app.include_router(backend_router)

# @app.get("/")
# def read_root():
#     return {"message": "Welcome to the Database Connection Service API"}
