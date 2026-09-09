# PRD — Domain-Agnostic, Format-Agnostic Agentic RAG System

Status: Draft v3 (multi-domain expansion — medical + financial)
Owner: Dia (BTech AI&ML, Semester 7 minor project)
Timeline: 40 days
Supervisor: Sir

---

## 1. Problem Statement

**Why this project exists (updated).**

- Sir now wants this system to prove a general architectural claim: that one
  RAG pipeline can serve **multiple domains** (medical, financial) coming in
  **multiple formats** (textual documents, tabular spreadsheets) without
  rewriting the core system for each new source.
- Two data sources are confirmed: financial data (sir's watchlist excel,
  schema may still change) and medical data (textual documents, being
  sourced by other students).
- A person asking a question shouldn't need to know or specify which domain
  their question belongs to — the system should figure that out.

**What this project solves:** an extensible RAG platform where adding a new
domain means writing one new extractor module, not rebuilding retrieval,
agentic reasoning, or evaluation from scratch.

---

## 2. Goals (MVP)

| # | Goal | Why it matters |
|---|------|-----------------|
| G1 | Build a **text extractor agent** (medical domain, DOCX documents) | One of the two modules sir explicitly asked for. DOCX is the confirmed real format — PDF is not part of the actual data |
| G2 | Build a **tabular extractor agent** (CSV/Excel — used by BOTH financial and medical domains) | Confirmed: medical data includes CSV (tcell antigen dataset, filtered human-subject dataset) alongside financial CSV/Excel — the tabular extractor must be domain-parameterized, not hardcoded to one domain |
| G3 | Both extractors output a shared, standardized schema (Knowledge Unit) | This is what makes the system format-agnostic — retrieval/agent code never needs to know if data came from a PDF or a spreadsheet |
| G4 | Domain-tagged storage (separate index per domain) | Keeps unrelated domains from polluting each other's retrieval results |
| G5 | **Domain router agent** — auto-detects which domain a question belongs to | Confirmed direction: system should be domain-agnostic from the user's perspective — they never manually pick a domain |
| G6 | Agentic query decomposition + hybrid retrieval + cited synthesis | Unchanged from the original plan — this is the reusable core that works regardless of domain |
| G7 | Eval harness with real numbers, per domain | Resume credibility; also proves the architecture generalizes, not just that it works once |
| G8 | Deployed, publicly accessible dashboard | Portfolio link |

---

## 3. Non-Goals (explicitly out of scope for MVP)

- OCR for scanned/image-based documents (native text extraction only)
- PDF ingestion — deferred to flexible/future scope. Confirmed real medical
  data arrives as DOCX and CSV, not PDF. Building PDF support now would be
  effort against a format that doesn't exist in the actual data
- Direct CSV/Excel upload through the live dashboard — tabular data is
  processed by the offline tabular extractor script first (unchanged from
  the previous plan)
- Cross-domain questions in a single query (e.g. one question that needs
  both medical and financial evidence) — router assumes single-domain
  questions unless sir confirms otherwise (open question, see §9)
- Support for more than 2 domains in the MVP — architecture should allow
  it, but only medical + financial need to actually work

---

## 4. Users

| User | What they need from this system |
|------|-----------------------------------|
| Sir / supervisor | Proof that the architecture generalizes — new domain in, no core rewrite needed |
| Viva panel / evaluators | A clear explanation of how domain routing and the shared schema work, and why this is harder than a single-domain RAG |
| Recruiters / hiring managers | A deployed, working system demonstrating platform-level system design, not just one RAG demo |
| You (Dia) | A system you built and fully understand end to end, including both extractor modules |

---

## 5. Core Features (MVP scope)

1. **Text extractor agent** — ingests medical DOCX documents, chunks them,
   tags each chunk `domain: "medical"`
2. **Tabular extractor agent** — ingests CSV/Excel for BOTH domains:
   financial (sir's watchlist) and medical (tcell antigen dataset, filtered
   human-subject dataset), tagged `domain: "financial"` or
   `domain: "medical"` per source, not hardcoded to one
3. **Knowledge Unit schema** — the shared contract both extractors output:
   `{id, domain, source_type, text, metadata}`
4. **Domain-tagged hybrid indexes** — `medical_collection` and
   `financial_collection`, each with dense (Chroma) + sparse (BM25)
5. **Domain router agent** — classifies an incoming question before
   retrieval starts, selects the correct collection
6. **Agentic chat interface** — question → domain routed → decomposed if
   complex → retrieved → cited answer
7. **Eval harness** — per-domain golden Q&A sets, faithfulness + citation
   accuracy + retrieval precision, reported separately per domain
8. **Upload dashboard** — accepts DOCX (medical) directly; both domains'
   CSV/Excel data enters via the offline tabular extractor script (not the
   live dashboard — unchanged from the earlier plan)

---

## 6. User Stories

- As sir, I want to see the same system answer both a medical question and
  a financial question correctly, without me telling it which domain to
  search, so I believe the architecture is genuinely general.
- As a viva evaluator, I want to ask why domain routing is necessary
  instead of just searching everything at once, and get a clear answer
  about retrieval noise and relevance.
- As Dia, I want both extractors to share the same downstream pipeline, so
  I only had to build retrieval, the agentic layer, and the eval harness
  once — not twice.

---

## 7. Success Metrics (resume-ready)

| Metric | Target | Scope |
|--------|--------|-------|
| Domain routing accuracy | ≥ 90% | Does the router send questions to the correct domain? |
| Faithfulness score (LLM-as-judge, 1–5 avg) | ≥ 4.0 | Measured separately per domain |
| Citation accuracy | ≥ 85% | Measured separately per domain |
| Retrieval precision@5 | ≥ 80% | Measured separately per domain |
| Golden eval set size | ≥ 15 Q&A per domain (30 total minimum, 50 if time allows) | Reduced from the single-domain plan given the tighter 40-day timeline |
| Retrieval ablation | precision@5 for dense-only, sparse-only, hybrid | Proves hybrid retrieval earns its complexity instead of assuming it — added after roadmap review |
| Naive-vs-agentic ablation | Accuracy: single-shot RAG (no decomposition/routing) vs. full pipeline | Proves the agentic layer (decomposition + routing) measurably improves results, not just adds complexity — added after roadmap review |

---

## 8. Flexible vs Fixed — what can change without breaking the plan

| Decision | Status | Notes |
|----------|--------|-------|
| 2 domains: medical + financial | **Fixed** | Confirmed with sir |
| Both extractors built by Dia | **Fixed** | Confirmed — no cross-student dependency for code, only for medical data delivery |
| Auto domain routing (agentic) | **Fixed** | Confirmed direction — not manual selection |
| Knowledge Unit shared schema | **Fixed** | This is what makes format-agnosticism real — do not let extractors drift from it |
| Excel/CSV schema (any domain) | **Flexible by design — confirmed** | Sir confirmed: column headings can change, new fields/sheets can be added, or it can stay the same. Tabular extractor must handle all three cases with zero hardcoded assumptions — already proven in the existing build, now a harder requirement since it must also work on medical CSV, not just financial |
| Medical document source | **Confirmed** | Arrives as DOCX + CSV, delivered in pieces over time (not one bulk drop) — not PDF. Real data: a tcell antigen experimental dataset (zip) and a filtered human-subject dataset, both CSV |
| DOCX support | **Fixed — primary format** | This is the real, confirmed medical text format, not a stretch goal |
| PDF support | **Flexible / deferred** | Not present in actual data; build only if time allows after DOCX + both extractors are solid |
| UI framework, deployment platform, embedding model, LLM model | **Flexible** | Unchanged from the original plan |

---

## 9. Confirmed Answers (previously open questions)

1. **Medical document format & delivery:** DOCX and CSV, not PDF. Two CSV
   sources already identified: a tcell antigen experimental dataset
   (delivered as a zip of the full experiment data) and a filtered
   human-subject dataset sir explicitly used. Data will arrive **in
   pieces over time**, not as one bulk drop — the ingestion pipeline
   should tolerate incremental additions (see TRD.md — `build_index.py`
   already uses upsert, which handles this for free).
2. **Cross-domain questions:** Not required. Sir confirmed medical and
   financial stay separate — the domain router does not need a "both"
   branch. Single-domain routing is sufficient.
3. **Excel/CSV schema volatility:** Sir confirmed column headings can
   change, new fields/sheets can be added, or the structure can stay the
   same — all three cases are possible and the tabular extractor must
   handle all of them without hardcoded assumptions.

---

## 10. Risks

| Risk | Mitigation |
|------|------------|
| 40 days is materially tighter than the original 45-day single-domain plan | Explicit cut order in ROADMAP.md; schema locked first to avoid rework |
| Medical data arrives in pieces over the build period | Design ingestion as incrementally re-runnable (already true — Chroma upsert handles this); don't assume a complete dataset upfront |
| Domain router misclassifies questions | Golden eval set includes intentionally ambiguous questions to measure this explicitly |
| Excel/CSV schema changes across either domain | Already mitigated — tabular extractor has no hardcoded column or sheet assumptions, confirmed necessary for both financial and medical CSV |
| Tabular extractor now must generalize across 2 domains, not 1 | Test explicitly against both financial and medical CSV samples before considering Phase 2 (ROADMAP.md) done |