"""
Central config — all values come from .env file.
Uses Groq for LLM calls, sentence-transformers locally for embeddings.
"""
import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-20b")
# The judge for the groundedness self-check (src/verifier.py) and for Phase 6's
# faithfulness scoring. It MUST be a different model family from LLM_MODEL:
# a model grading its own output is a biased judge, since the same weights
# produced both the claim and the verdict. qwen (Alibaba) vs gpt-oss (OpenAI)
# is a genuine lineage split; gpt-oss-120b would only be a bigger sibling and
# would buy no independence at all.
VERIFIER_MODEL = os.getenv("VERIFIER_MODEL", "qwen/qwen3.8-27b")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_store")
GENERATED_DIR = os.getenv("GENERATED_DIR", "data/generated")

if not GROQ_API_KEY:
    raise EnvironmentError(
        "GROQ_API_KEY not found. Copy .env.example to .env and add your Groq key.\n"
        "Get a free key at: https://console.groq.com"
    )