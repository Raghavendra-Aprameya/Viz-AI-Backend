import requests
from typing import Dict, Any

LLM_SERVICE_URL = "http://localhost:8001"

def call_llm_simple_endpoint() -> Dict[str, Any]:
    """
    Call the simple endpoint from LLM service
    """
    try:
        response = requests.get(f"{LLM_SERVICE_URL}/api/simple")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to call LLM service: {str(e)}")
