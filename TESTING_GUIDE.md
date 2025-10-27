# API Testing Guide - UPDATED
## Setup Instructions

### 1. Start LLM Service (Port 8001)
```bash
cd vizAi_LLM_service-main
python run_llm_service.py
```

### 2. Start Backend Service (Port 8000)
```bash
cd Viz-AI-Backend
python run_backend.py
```

## Postman Testing

### Test 1: LLM Service Direct Call
- **Method**: GET
- **URL**: `http://localhost:8001/api/simple`
- **Expected Response**:
```json
{
    "name": "Lamborghini"
}
```

### Test 2: Backend Service Call (which calls LLM Service)
- **Method**: GET
- **URL**: `http://localhost:8000/api/v1/llm/simple`
- **Expected Response**:
```json
{
    "name": "Lamborghini"
}
```

### Test 3: Backend Service Health Check
- **Method**: GET
- **URL**: `http://localhost:8000/`
- **Expected Response**:
```json
{
    "message": "Viz-AI Backend Service is running!"
}
```

### Test 4: LLM Service Documentation
- **URL**: `http://localhost:8001/docs`
- This will show the FastAPI interactive documentation

### Test 5: Backend Service Documentation
- **URL**: `http://localhost:8000/docs`
- This will show the FastAPI interactive documentation

## Verification Steps

1. **LLM Service Health**: Call `http://localhost:8001/api/simple` directly
2. **Backend Service Health**: Call `http://localhost:8000/api/v1/llm/simple`
3. **Integration Test**: Both should return the same response
4. **Error Handling**: Stop LLM service and call backend endpoint to test error handling

