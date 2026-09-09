"""
Central config — all values come from .env file.
Uses Groq for LLM calls, sentence-transformers locally for embeddings.
"""
import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_store")
GENERATED_DIR = os.getenv("GENERATED_DIR", "data/generated")

if not GROQ_API_KEY:
    raise EnvironmentError(
        "GROQ_API_KEY not found. Copy .env.example to .env and add your Groq key.\n"
        "Get a free key at: https://console.groq.com"
    )