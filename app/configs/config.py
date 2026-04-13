from dotenv import load_dotenv
import os
from app.core.settings import settings
load_dotenv()
from langchain_openai import ChatOpenAI 
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
llm = ChatOpenAI(
    model=MODEL,
    temperature=0.3,
    api_key=settings.OPENAPI_API_KEY
)