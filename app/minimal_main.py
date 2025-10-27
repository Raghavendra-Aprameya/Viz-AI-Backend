from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests

# Create a minimal FastAPI app instance
app = FastAPI(title="Viz-AI Backend Service", description="Simple API for testing")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

LLM_SERVICE_URL = "http://localhost:8001"

def call_llm_simple_endpoint():
    """
    Call the simple endpoint from LLM service
    """
    try:
        response = requests.get(f"{LLM_SERVICE_URL}/api/simple")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to call LLM service: {str(e)}")

@app.get("/api/v1/llm/simple")
def get_simple_from_llm():
    """
    Endpoint to call the simple API from LLM service
    """
    try:
        result = call_llm_simple_endpoint()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root():
    return {"message": "Viz-AI Backend Service is running!"}
