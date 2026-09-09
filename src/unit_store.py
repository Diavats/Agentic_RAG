"""
On-disk store for extracted KnowledgeUnits, one file per domain.

Why this exists as a separate step from indexing: extraction is EXPENSIVE and
indexing is cheap. The tabular extractor makes one Groq call per row, so
re-running it to fix an indexing bug would burn real rate limit for no reason.
Units are extracted once, persisted here, and indexed as many times as needed.

Why it merges instead of overwriting: medical data arrives in pieces (PRD
section 10). Ingesting the second CSV must add to the first, not replace it —
the same failure that made the BM25 index silently lose its corpus.
"""
import json
from pathlib import Path

from src.config import GENERATED_DIR
from src.schema import KnowledgeUnit


def units_path(domain: str) -> Path:
    return Path(GENERATED_DIR) / f"{domain}_units.json"


def load_units(domain: str) -> list[KnowledgeUnit]:
    """Every unit extracted so far for this domain. Empty list if none."""
    path = units_path(domain)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [KnowledgeUnit.model_validate(record) for record in json.load(f)]


def save_units(units: list[KnowledgeUnit], domain: str) -> Path:
    """Overwrite this domain's store. Callers that are adding rather than
    replacing should use merge_units()."""
    path = units_path(domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([u.model_dump() for u in units], f, indent=2, ensure_ascii=False)
    return path


def merge_units(new_units: list[KnowledgeUnit], domain: str) -> tuple[list[KnowledgeUnit], int, int]:
    """Add new_units to the domain store, keyed by ID. Returns
    (all_units, n_added, n_updated).

    Re-ingesting the same source file updates its units in place, because
    make_unit_id() is deterministic over (domain, source_type, filename,
    position). Ingesting a different file appends.
    """
    existing = {u.id: u for u in load_units(domain)}
    before = len(existing)
    updated = sum(1 for u in new_units if u.id in existing)

    for unit in new_units:
        existing[unit.id] = unit

    merged = list(existing.values())
    save_units(merged, domain)
    return merged, len(merged) - before, updated
