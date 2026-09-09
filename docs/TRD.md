# TRD — Domain-Agnostic, Format-Agnostic Agentic RAG System

Companion to PRD.md. Implementation should not deviate from this without
updating the doc first.

---

## 1. Architecture Overview

```
INGESTION (offline / admin, per domain — arrives incrementally, in pieces)
┌─────────────────────────────┐      ┌─────────────────────────────┐
│  TEXT EXTRACTOR AGENT         │      │  TABULAR EXTRACTOR AGENT     │
│  medical DOCX documents       │      │  CSV/XLSX — used by BOTH      │
│  docx_loader -> chunker.py     │      │  financial AND medical        │
│  (PDF: flexible/deferred)      │      │  tabular_loader ->            │
│                                │      │  narrative_generator.py       │
│                                │      │  domain passed as a parameter │
└───────────────┬───────────────┘      └───────────────┬───────────────┘
                 │  Knowledge Unit                       │  Knowledge Unit
                 │  {id, domain="medical",                │  {id, domain="financial"|"medical",
                 │   source_type="textual", text, metadata}│   source_type="tabular", text, metadata}
                 v                                        v
      ┌─────────────────────┐                  ┌─────────────────────┐
      │  medical_collection   │                  │  financial_collection│
      │  Chroma + BM25         │                  │  Chroma + BM25        │
      └───────────┬───────────┘                  └───────────┬───────────┘
                  │      ▲                                    │
                  │      └──── medical CSV rows also land here (tagged domain="medical")
                  └──────────────────┬─────────────────────────┘
                                     v
```

**Important correction from the original diagram:** the tabular extractor
is NOT financial-only. It's called once per data source with a `domain`
parameter — the same code processes sir's stock watchlist (domain=
"financial") and the tcell antigen / human-subject CSVs (domain="medical").
Its Knowledge Units land in whichever collection matches that parameter.

```
QUERY TIME (live, per question)
                  ┌──────────────────────────────────┐
                  │   DOMAIN ROUTER AGENT               │
                  │   classifies question ->             │
                  │   "medical" | "financial"            │
                  └───────────────┬───────────────────────┘
                                  v
                  ┌──────────────────────────────────┐
                  │   QUERY PLANNER AGENT (existing)     │
                  │   decomposes if complex               │
                  └───────────────┬───────────────────────┘
                                  v
                  ┌──────────────────────────────────┐
                  │   HYBRID RETRIEVAL                   │
                  │   (queries the ROUTED collection only)│
                  └───────────────┬───────────────────────┘
                                  v
                  ┌──────────────────────────────────┐
                  │   SYNTHESIS AGENT (existing)          │
                  │   cited, grounded answer               │
                  └──────────────────────────────────────┘
```

**Why this shape:** the Knowledge Unit schema is the seam between
"format-specific" (extractors) and "format-agnostic" (everything
downstream). Retrieval, the query planner, and synthesis never know or
care whether a chunk originally came from a PDF or a spreadsheet row —
they only see `{id, domain, source_type, text, metadata}`. That's what
makes adding a third domain later a one-module change, not a rewrite.

---

## 2. Tech Stack

| Layer | Tool | Why | Status |
|-------|------|-----|--------|
| Language | Python 3.11+ | Ecosystem standard | unchanged |
| Tabular extractor | pandas + openpyxl + OpenAI narrative generation | Already built and tested. Now called with a `domain` parameter — same code serves financial and medical CSV | done, needs domain param added |
| Text extractor | python-docx + custom chunker | DOCX is the confirmed real medical format. Native paragraph extraction, no OCR | new |
| PDF support | pypdf (optional) | Deferred — not present in real data, add only if time allows | flexible / deferred |
| Chunking (medical docs) | Recursive character splitter, ~500 tokens, 50 overlap | Documents are long-form prose, need splitting unlike tabular rows | new |
| Dense embeddings | sentence-transformers (`all-MiniLM-L6-v2`) | Free, local, CPU-only | unchanged |
| Vector store | ChromaDB (persistent, file-based), **one collection per domain** | Domain separation prevents retrieval noise between unrelated corpora | modified |
| Sparse retrieval | rank-bm25, **one index per domain** | Same reasoning as above | modified |
| Fusion | Reciprocal Rank Fusion (custom) | Already built, domain-agnostic by design | unchanged |
| Domain router | LLM classification call (OpenAI, low temperature) | Simple, accurate enough at 2-domain scale; can be swapped for a cheaper embedding-similarity classifier later if latency matters | new |
| Query decomposition + synthesis | OpenAI API | Already built, domain-agnostic by design | unchanged |
| Eval | Custom harness, run separately per domain | To be built | new scope |
| Backend | FastAPI | Unchanged from previous plan | planned |
| Frontend | Streamlit | Unchanged from previous plan | planned |
| Deployment | Streamlit Community Cloud + Render | Unchanged from previous plan | planned |

---

## 3. The Knowledge Unit Schema (lock this before writing extractor code)

```json
{
  "id": "string — stable, unique across the whole system, e.g. 'financial_row_0007' or 'medical_chunk_0032'",
  "domain": "medical | financial",
  "source_type": "textual | tabular",
  "text": "string — the retrievable content (narrative story OR document chunk)",
  "metadata": {
    "source_file": "string — original filename",
    "generated_at": "ISO timestamp",
    "extra": "domain-specific fields go here, e.g. {ticker, quarter} for financial or {document_title, section} for medical"
  }
}
```

**Rule:** both extractors MUST output exactly this shape. Anything
domain-specific belongs inside `metadata.extra`, never as a top-level
field — this is what keeps `build_index.py`, `hybrid_retrieval.py`, and
`agent.py` from ever needing domain-specific code.

---

## 4. Module / File Structure (target state)

```
agentic-rag/
├── scripts/
│   └── generate_stories_from_excel.py   [offline — tabular extractor entrypoint]
├── src/
│   ├── config.py                         [done]
│   ├── schema.py                         [new — Knowledge Unit dataclass/Pydantic model]
│   ├── extractors/
│   │   ├── text_extractor.py             [new — medical DOCX -> Knowledge Units; PDF loader optional/deferred]
│   │   └── tabular_extractor.py          [done, wraps existing loader.py + narrative_generator.py — now accepts a `domain` param, called separately for financial and medical CSV sources]
│   ├── chunker.py                        [new — used only by text_extractor.py]
│   ├── build_index.py                    [modified — accepts a domain param, builds per-domain collections]
│   ├── hybrid_retrieval.py               [modified — accepts a domain param]
│   ├── domain_router.py                  [new — classifies question -> domain]
│   ├── agent.py                          [modified — calls domain_router.py before retrieval]
│   ├── eval/
│   │   ├── golden_dataset_medical.json   [new]
│   │   ├── golden_dataset_financial.json [new]
│   │   ├── run_eval.py                   [new — runs per domain]
│   │   └── metrics.py                    [new]
│   └── api/
│       └── main_api.py                   [new — FastAPI wrapper]
├── app/
│   └── streamlit_app.py                  [new — UI, built last]
├── data/
│   ├── sample_stocks.csv                 [done — financial domain]
│   ├── sample_products.csv               [done — generic-format proof, keep for the demo]
│   ├── medical_tcell_antigen/            [new — sir's zipped experimental dataset, CSV, arrives in pieces]
│   └── medical_human_filtered/           [new — filtered human-subject dataset, CSV, arrives in pieces]
├── docs/
│   ├── PRD.md / TRD.md / RULES_AND_GOALS.md / ROADMAP.md
├── requirements.txt
├── .env.example
└── README.md
```

---

## 5. Domain Router — design detail

- Input: the raw user question.
- Output: `"medical"` or `"financial"` (single label — cross-domain
  questions are out of scope per PRD §3 unless sir says otherwise).
- Implementation: one LLM call, low temperature, structured output
  (`{"domain": "medical" | "financial"}` via Pydantic/instructor).
- Fallback: if the classifier is not confident (add a `confidence` field
  to the structured output), default to asking the user to clarify rather
  than guessing — cheap to add, avoids silent misrouting.
- Eval requirement: the golden Q&A sets (PRD §7) should include a handful
  of intentionally ambiguous questions specifically to measure routing
  accuracy, not just answer quality.

---

## 6. API Contract (FastAPI) — updated

| Endpoint | Method | Input | Output |
|----------|--------|-------|--------|
| `/extract/text` | POST | file upload (DOCX) | `{status, chunks_created, domain: "medical"}` |
| `/extract/tabular` | POST (internal/admin use, not public UI) | `{csv_path, domain}` | `{status, stories_generated, domain}` — domain is explicit input, not hardcoded |
| `/index` | POST | `{domain}` | `{status, documents_indexed}` |
| `/ask` | POST | `{question}` (no domain param — router decides) | `{question, routed_domain, subqueries, retrieved_ids, answer}` |
| `/eval/run` | GET | `{domain}` | `{faithfulness_avg, citation_accuracy, retrieval_precision, routing_accuracy, per_case_results}` |

---

## 7. Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Runs on CPU only | Yes — no GPU dependency anywhere |
| Domain routing latency | < 1.5s (single LLM call, small prompt) |
| End-to-end query latency | < 8s including routing |
| Cost per demo session | < $0.75 (higher than single-domain plan due to routing call) |
