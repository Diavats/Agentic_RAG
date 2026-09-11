"""
Narrative generation agent — Groq (Llama 3.3-70B).
Turns one structured row (any schema) into a natural-language story.
"""
from groq import Groq
from src.config import GROQ_API_KEY, LLM_MODEL
from src.llm_cache import cached_completion

client = Groq(api_key=GROQ_API_KEY)

NARRATIVE_PROMPT = """You are a domain analyst. Below is one structured record.
Write a clear, coherent narrative (120-180 words) that synthesizes this record
into a story a human analyst could read and understand quickly.

Rules:
- Use only the information given. Do not invent facts.
- Mention every field that has a meaningful (non-N/A) value.
- Write in plain prose, not bullet points.
- Do not just repeat the raw field names — turn them into natural sentences.

Record:
{record_text}

Narrative:"""


def row_to_text(row: dict) -> str:
    lines = []
    for key, value in row.items():
        if key == "row_id":
            continue
        if value is None or str(value).strip().upper() in ("N/A", "NAN", ""):
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def generate_narrative(row: dict) -> str:
    record_text = row_to_text(row)
    return cached_completion(
        client, LLM_MODEL, NARRATIVE_PROMPT.format(record_text=record_text), temperature=0.3
    )


def generate_all(rows: list[dict]) -> list[dict]:
    stories = []
    for row in rows:
        story_text = generate_narrative(row)
        stories.append({
            "row_id": row["row_id"],
            "narrative": story_text,
            "source_row": row,
        })
        print(f"  generated {row['row_id']}")
    return stories