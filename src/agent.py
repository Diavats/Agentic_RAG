"""
Agentic layer — Groq (Llama 3.3-70B).
Two agents:
  1. Query planner  — decomposes complex questions into sub-questions.
  2. Synthesis agent — fuses retrieved chunks into one cited answer.
"""
import json
from groq import Groq
from src.config import GROQ_API_KEY, LLM_MODEL
from src.hybrid_retrieval import hybrid_search

client = Groq(api_key=GROQ_API_KEY)

DECOMPOSE_PROMPT = """You are a query planning agent. Given a user question, decide if it
needs to be broken into multiple sub-questions to be answered well.

If it's simple, return a JSON list with just the original question.
If it's complex (compares multiple entities, spans multiple categories, or has
multiple parts), break it into 2-4 focused sub-questions.

Return ONLY a JSON list of strings, nothing else. No explanation.

Question: {question}"""

SYNTHESIS_PROMPT = """Answer the user's question using ONLY the retrieved context below.
Every claim must be traceable to a specific source. Cite sources inline like [S1], [S2].
If the context doesn't fully answer the question, say plainly what's missing.

Question: {question}

Retrieved context:
{context}

Answer (with citations):"""


def decompose_query(question: str) -> list[str]:
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": DECOMPOSE_PROMPT.format(question=question)}],
        temperature=0,
    )
    raw = response.choices[0].message.content.strip()
    try:
        subqueries = json.loads(raw)
        if isinstance(subqueries, list) and subqueries:
            return subqueries
    except json.JSONDecodeError:
        pass
    return [question]


def retrieve_for_subqueries(subqueries: list[str], dataset_name: str, k: int = 4) -> list[dict]:
    seen: dict[str, dict] = {}
    for sq in subqueries:
        for doc in hybrid_search(sq, dataset_name, k=k):
            seen[doc["row_id"]] = doc
    return list(seen.values())


def synthesize_answer(question: str, retrieved: list[dict]) -> str:
    context_blocks = [
        f"[S{i}] (row {doc['row_id']}): {doc['text']}"
        for i, doc in enumerate(retrieved, start=1)
    ]
    context = "\n\n".join(context_blocks)
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": SYNTHESIS_PROMPT.format(question=question, context=context)}],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


def ask(question: str, dataset_name: str) -> dict:
    subqueries = decompose_query(question)
    print(f"  Decomposed into {len(subqueries)} sub-quer{'y' if len(subqueries)==1 else 'ies'}: {subqueries}")
    retrieved = retrieve_for_subqueries(subqueries, dataset_name)
    print(f"  Retrieved {len(retrieved)} unique source documents")
    answer = synthesize_answer(question, retrieved)
    return {
        "question": question,
        "subqueries": subqueries,
        "retrieved_ids": [d["row_id"] for d in retrieved],
        "answer": answer,
    }