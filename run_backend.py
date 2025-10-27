#!/usr/bin/env python3
"""
Minimal startup script for the Backend service
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.minimal_main:app",
        host="localhost",
        port=8000,
        reload=True
    )
