"""
Tabular Extractor Agent — Phase 2.

Wraps the existing, verified loader (`src.loader.load_tabular`) and
narrative generator (`src.narrative_generator.generate_narrative`) —
neither is modified here — and adds the two things Phase 2 requires:

1. A required `domain` parameter (never inferred, never defaulted)
2. KnowledgeUnit output instead of the old ad-hoc
   {row_id, narrative, source_row} dict

Cross-domain by design: the same function ingests financial CSVs and
medical CSVs. Domain is metadata the caller supplies, not something
this code infers from the data — that is what makes the extractor
genuinely format-agnostic rather than two pipelines wearing one name.

See docs/AGENTS.md, Agent 6, for the full spec this implements.
"""
from pathlib import Path
from typing import Literal

from src.loader import load_tabular
from src.narrative_generator import generate_narrative
from src.schema import KnowledgeUnit, KnowledgeUnitMetadata

Domain = Literal["medical", "financial"]


def extract_tabular(file_path: str, domain: Domain) -> list[KnowledgeUnit]:
    """Turn any CSV/Excel file into a list of KnowledgeUnits.

    Args:
        file_path: path to a .csv or .xlsx file. Any schema — no
            hardcoded column names or sheet assumptions.
        domain: "medical" or "financial". REQUIRED — raises if missing
            or invalid. Never defaulted, never guessed from the data.

    Returns:
        One KnowledgeUnit per row, source_type="tabular", id following
        "{domain}_tabular_{index:04d}".
    """
    if domain not in ("medical", "financial"):
        raise ValueError(
            f"domain must be 'medical' or 'financial', got: {domain!r}. "
            "This extractor never guesses the domain — the caller must "
            "supply it explicitly."
        )

    rows = load_tabular(file_path)
    source_file = Path(file_path).name

    units: list[KnowledgeUnit] = []
    for i, row in enumerate(rows):
        narrative = generate_narrative(row)
        extra = {k: v for k, v in row.items() if k != "row_id"}

        unit = KnowledgeUnit(
            id=f"{domain}_tabular_{i:04d}",
            domain=domain,
            source_type="tabular",
            text=narrative,
            metadata=KnowledgeUnitMetadata(
                source_file=source_file,
                extra=extra,
            ),
        )
        units.append(unit)
        print(f"  extracted {unit.id}")

    return units


if __name__ == "__main__":
    # Sanity check: same function, two unrelated schemas, two domains.
    # This is the cross-domain proof — no code path here branches on
    # which dataset is being read.
    print("=== financial: data/sample_stocks.csv ===")
    financial_units = extract_tabular("data/sample_stocks.csv", domain="financial")
    print(f"{len(financial_units)} units extracted\n")
    print(financial_units[0].model_dump_json(indent=2))

    print("\n=== medical: data/medical_placeholder.csv ===")
    medical_units = extract_tabular("data/medical_placeholder.csv", domain="medical")
    print(f"{len(medical_units)} units extracted\n")
    print(medical_units[0].model_dump_json(indent=2))