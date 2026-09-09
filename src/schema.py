"""
The Knowledge Unit — the single shared shape every extractor must output,
regardless of domain (medical / financial) or format (textual / tabular).

This is the seam in the architecture: everything BEFORE this file is
format-specific (loaders, narrative generation, chunking). Everything
AFTER this file (indexing, retrieval, the agent) only ever sees a
KnowledgeUnit and never needs to know or care where it came from.

Do not let any downstream module reach into extractor-specific logic.
If a new field is needed, it goes in `metadata.extra` — never as a new
top-level field, or every extractor + every downstream module needs
updating together.
"""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class KnowledgeUnitMetadata(BaseModel):
    """Common metadata every Knowledge Unit carries, plus a free-form
    'extra' bucket for domain-specific fields that don't need to be
    shared across domains."""

    source_file: str = Field(..., description="Original filename this unit came from")
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO timestamp of when this unit was created",
    )
    extra: dict = Field(
        default_factory=dict,
        description=(
            "Domain-specific fields live here, e.g. {'ticker': 'JGCHEM', "
            "'quarter': '2026-Q1'} for financial, or "
            "{'document_title': '...', 'section': '...'} for medical. "
            "Downstream code (indexing, retrieval, agent) never reads "
            "specific keys from here — it's for humans debugging or for "
            "future domain-specific filtering, not for the core pipeline."
        ),
    )


class KnowledgeUnit(BaseModel):
    """The shared contract. Both the text extractor (medical DOCX) and
    the tabular extractor (financial + medical CSV/Excel) must produce
    instances of this exact shape."""

    id: str = Field(
        ...,
        description=(
            "Stable, unique across the WHOLE system, not just within one "
            "dataset. Convention: '{domain}_{source_type}_{index:04d}', "
            "e.g. 'financial_tabular_0007' or 'medical_textual_0032'."
        ),
    )
    domain: Literal["medical", "financial"] = Field(
        ..., description="Which domain this unit belongs to — set by the caller, never inferred by the extractor."
    )
    source_type: Literal["textual", "tabular"] = Field(
        ..., description="Which format this unit came from — determines which extractor produced it, not which domain."
    )
    text: str = Field(
        ..., description="The retrievable content: a narrative story (tabular) or a document chunk (textual)."
    )
    metadata: KnowledgeUnitMetadata


# ---------------------------------------------------------------------------
# Example instances — one per domain, as required by ROADMAP.md Phase 1.
# These aren't executed automatically; they're here as a live reference so
# anyone extending this schema can see it actually fits both domains before
# writing extractor code against it.
# ---------------------------------------------------------------------------

EXAMPLE_FINANCIAL_UNIT = KnowledgeUnit(
    id="financial_tabular_0007",
    domain="financial",
    source_type="tabular",
    text=(
        "JGCHEM, a supplier of Zinc Oxide to auto OEMs and tyre makers, "
        "posted profitable growth this quarter with sales up 15.2% and "
        "operating profit up 103.8% quarter-on-quarter, driven by strong "
        "auto production and tyre vulcanization demand."
    ),
    metadata=KnowledgeUnitMetadata(
        source_file="sample_stocks.csv",
        extra={"ticker": "JGCHEM", "quarter": "2026-Q1", "sector": "Auto OEMs & Tyre Makers"},
    ),
)

EXAMPLE_MEDICAL_UNIT = KnowledgeUnit(
    id="medical_tabular_0012",
    domain="medical",
    source_type="tabular",
    text=(
        "In the tcell antigen experiment dataset, sample TC-014 showed a "
        "strong positive response to antigen panel B, with elevated "
        "activation markers observed at the 48-hour timepoint in the "
        "filtered human-subject cohort."
    ),
    metadata=KnowledgeUnitMetadata(
        source_file="medical_tcell_antigen.csv",
        extra={"sample_id": "TC-014", "antigen_panel": "B", "cohort": "human-subject-filtered"},
    ),
)

# A textual example too, since source_type varies independently of domain —
# this is what a medical DOCX chunk will look like once the text extractor
# (Phase 3) exists.
EXAMPLE_MEDICAL_TEXTUAL_UNIT = KnowledgeUnit(
    id="medical_textual_0003",
    domain="medical",
    source_type="textual",
    text=(
        "Section 4.2 of the guideline document: [placeholder — this is "
        "where a ~500-token chunk of an actual medical DOCX document will "
        "land once real documents arrive]."
    ),
    metadata=KnowledgeUnitMetadata(
        source_file="placeholder.docx",
        extra={"section": "4.2", "document_title": "placeholder"},
    ),
)


if __name__ == "__main__":
    # Quick sanity check — run with: python -m src.schema
    for unit in (EXAMPLE_FINANCIAL_UNIT, EXAMPLE_MEDICAL_UNIT, EXAMPLE_MEDICAL_TEXTUAL_UNIT):
        print(unit.model_dump_json(indent=2))
        print("---")