# AGENTS.md — Agent Specifications

Every agent in this system is documented here: its role, goal,
constraints, inputs, outputs, and how it fits into the overall pipeline.
Update this file whenever an agent's behaviour changes or a new agent is
added.

---

## Overview — Agent Map

```
INGESTION PATH (offline)
┌─────────────────────────┐    ┌──────────────────────────────┐
│  Narrative Generator     │    │  (future) Text Extractor      │
│  Agent                   │    │  Agent                         │
│  [BUILT ✅]              │    │  [Phase 3, NOT BUILT]          │
└────────────┬─────────────┘    └──────────────┬───────────────┘
              │ KnowledgeUnit                   │ KnowledgeUnit
              └──────────────┬──────────────────┘
                             ▼
                    Shared Knowledge Index
                    (per-domain: medical / financial)
                    [Phase 4 — NOT BUILT]

QUERY PATH (live)
User Question
      ▼
┌─────────────────────────┐
│  Domain Router Agent     │
│  [Phase 5, NOT BUILT]    │
└────────────┬─────────────┘
             ▼
┌─────────────────────────┐
│  Query Planner Agent     │
│  [BUILT ✅]              │
└────────────┬─────────────┘
             ▼
     Hybrid Retrieval
     (routed collection)
             ▼
┌─────────────────────────┐
│  Synthesis Agent         │
│  [BUILT ✅]              │
└────────────┬─────────────┘
             ▼
     Cited Answer
```

---

## Agent 1 — Narrative Generator Agent

**Status:** ✅ Built, verified working on Dia's laptop
**File:** `src/narrative_generator.py`
**Phase built:** Phase 0

### Role
Automates the manual workflow sir was doing by hand in Gemini: given one
structured data row (any schema), it writes a 120–180 word analyst-style
narrative that a human can read and understand. This narrative becomes the
unit of retrieval in the downstream index.

### Goal
Turn tabular data (any domain, any schema) into rich, searchable prose —
without hallucinating, without requiring the columns to be pre-labelled
in any specific way.

### Constraints
- Must use ONLY the information present in the row — no invented facts
- Must handle any set of column names without code changes (schema-agnostic)
- Must skip None, N/A, NaN, and empty values silently
- Output must be plain prose, not bullet points
- Token limit: ~180 words max to keep each story a coherent retrieval unit

### Input
A Python `dict` representing one row from a CSV/Excel file. Keys are
column names (whatever they happen to be). Values are the row's data.
A special `row_id` key (added by `loader.py`) is always present and must
be excluded from the narrative text.

### Output
A plain-text string: the generated narrative story. Wrapped by
`generate_all()` into a list of `{row_id, narrative, source_row}` dicts
that get saved to `data/generated/{dataset_name}_stories.json`.

### How it works
1. `row_to_text(row)` formats the row as `"Field: Value\nField: Value..."` lines
2. This is injected into a fixed system prompt that instructs the LLM to
   write a coherent prose narrative
3. One Groq API call per row, `temperature=0.3` for consistent output
4. Uses the model ID from `config.LLM_MODEL` — **never hardcode a model
   ID directly in this file, always read from config**

### What changes in Phase 2
This agent stays structurally identical. The only change: its output gets
wrapped into a `KnowledgeUnit` (from `schema.py`) instead of the current
ad-hoc `{row_id, narrative, source_row}` dict — and a `domain` parameter
is added so the caller can tag the output correctly.

### Known issues / watch-outs
- Groq model IDs in `config.py` have been deprecated twice — if this
  agent starts throwing 404 or 400 errors, the model was deprecated.
  Check `console.groq.com/docs/deprecations` and update `config.py`.

---

## Agent 2 — Query Planner Agent

**Status:** ✅ Built, verified working on Dia's laptop
**File:** `src/agent.py` — `decompose_query()` function
**Phase built:** Phase 0

### Role
Decides whether an incoming question is simple (answerable with one
retrieval pass) or complex (needs breaking into sub-questions first).
For complex questions, produces a list of focused sub-queries. This is
what makes the system "agentic" — not just a single LLM call followed by
a search, but a planning step that reasons about the question before
touching the index.

### Goal
Maximise retrieval recall for complex, multi-part, or comparative
questions by ensuring each distinct information need is sent to the index
as its own focused query.

### Constraints
- Must return a valid JSON list of strings — nothing else, no preamble
- If the JSON parse fails for any reason, must fall back to returning
  `[original_question]` (single-item list) — never crash
- Sub-queries: 2–4 maximum. If a question has more than 4 distinct parts,
  collapse the least distinct ones
- Temperature: 0 (deterministic — question decomposition must be
  reproducible, not creative)
- Must NOT add sub-queries that aren't implied by the original question —
  this isn't question expansion, it's decomposition

### Input
A plain string: the user's raw question.

### Output
A Python `list[str]`: either `[original_question]` (simple) or 2–4
focused sub-questions (complex).

### How it works
1. Sends the question to the LLM with a strict prompt: return ONLY a
   JSON list, one item per sub-question
2. Parses the JSON. On any parse failure, returns `[question]` as fallback
3. The returned list is passed to `retrieve_for_subqueries()` which runs
   hybrid retrieval for each item and deduplicates results

### What changes in Phase 5
In Phase 5 (domain router), this agent's position in the pipeline shifts:
the domain router runs FIRST, selects the correct collection, and THEN
the query planner runs against only that collection. The planner's own
code doesn't change — it just receives a pre-selected collection name
instead of a hardcoded one.

---

## Agent 3 — Synthesis Agent

**Status:** ✅ Built, verified working on Dia's laptop
**File:** `src/agent.py` — `synthesize_answer()` function
**Phase built:** Phase 0

### Role
Takes a list of retrieved document chunks (from hybrid search) and the
original question, and produces a single grounded, cited answer. Every
claim must trace back to a retrieved source, cited as [S1], [S2], etc.
This agent is the hallucination guard — it is explicitly instructed to
state what's missing rather than invent an answer.

### Goal
Produce a coherent, human-readable answer that is 100% grounded in the
retrieved context. No claims beyond what the sources say. Transparency
over completeness — "I don't have enough context to answer X" is a
correct output.

### Constraints
- Must cite every claim with a bracketed source reference [S1], [S2] etc.
- Must explicitly state when the context is insufficient — never fill gaps
  with hallucinated information
- Temperature: 0.2 (low but not zero — some fluency variation in synthesis
  is acceptable, pure determinism is not needed here)
- Context window limit: if more than ~8 sources are retrieved, the prompt
  can exceed Groq's context. Currently retrieves top 4-6 per sub-query
  with deduplication — stay within this range

### Input
- `question: str` — the original user question
- `retrieved: list[dict]` — list of `{row_id, text, score}` dicts from
  hybrid search

### Output
A plain string: the synthesized answer with inline citations.

### How it works
1. Formats retrieved docs as numbered context blocks:
   `[S1] (row row_0003): <text>`, `[S2] (row row_0007): <text>` etc.
2. Sends question + numbered context to LLM with a strict prompt:
   answer only from the context, cite every claim, flag gaps
3. Returns the raw LLM response string

### What changes in Phase 6 (eval harness)
The eval harness will send the synthesis agent's output to an LLM-as-judge
to score faithfulness (does every claim actually appear in the cited
source?) and citation accuracy (does [S2] actually support the claim it's
attached to?). The judge MUST be a different model than the one that
generated the answer — same-model grading is a biased judge. The agent
itself doesn't change — just measured. Phase 6 also adds two ablations
(retrieval method, and naive vs. agentic pipeline) — see ROADMAP.md Phase
6 for details; neither requires changes to this agent's code.

---

## Agent 4 — Domain Router Agent

**Status:** ❌ Not built — Phase 5
**File (planned):** `src/domain_router.py`

### Role
The first thing that runs at query time. Receives the raw user question
and returns a single label: `"medical"` or `"financial"`. This label
determines which collection the query planner + hybrid retrieval will
search against.

### Goal
Make the system domain-agnostic from the user's perspective — they never
manually select which domain to search. The router infers it from the
question's language, terminology, and context.

### Constraints
- Output must be STRICTLY `"medical"` or `"financial"` — no other values,
  no prose, no explanation in the output. Use structured output
  (Pydantic + instructor) to enforce this at the code level, not just
  the prompt level
- Must also return a `confidence` field (0.0–1.0). If confidence < 0.7,
  the system should ask the user for clarification rather than guess
  (prevents silent misrouting — failing loudly is better than a
  confidently wrong answer)
- Temperature: 0 (classification must be deterministic)
- Latency budget: < 1.5 seconds (single small LLM call, short prompt —
  keep the classification prompt tight)
- Must NOT use retrieved content to make this decision — routing happens
  BEFORE retrieval, not after

### Input
A plain string: the user's raw question.

### Output
A Pydantic model instance: `{domain: "medical" | "financial", confidence: float}`

### How it will work (design intent for Phase 5)
1. Short classification prompt: "Classify this question as either medical
   or financial. Return JSON only."
2. `instructor` library enforces the Pydantic output shape — no free-text
   responses accepted
3. If `confidence < 0.7`: return a structured clarification request to the
   user ("Did you mean to ask about medical data or financial data?")
4. If `confidence >= 0.7`: pass `domain` to the query planner + hybrid
   retrieval as the collection selector

### Eval requirement (Phase 6)
The golden Q&A sets must include ~5 intentionally ambiguous questions
(e.g. "What is the growth trend?" — could be financial growth or tumor
growth) specifically to measure routing accuracy. Target: ≥ 90% correct
routing across the full eval set.

---

## Agent 5 — Text Extractor Agent

**Status:** ❌ Not built — Phase 3
**File (planned):** `src/extractors/text_extractor.py`

### Role
Ingests medical DOCX documents, splits them into retrievable chunks, and
wraps each chunk as a `KnowledgeUnit` with `domain="medical"` and
`source_type="textual"`.

### Goal
Turn long-form prose documents (Word files from sir's lab / other
students) into the same `KnowledgeUnit` shape that the tabular extractor
produces — so the downstream index, retrieval, and agent code never needs
to know whether content came from a document or a spreadsheet.

### Constraints
- DOCX format only for MVP — PDF is deferred (not in real data)
- Chunk size: **derived from the embedding model, never hardcoded** —
  `SentenceTransformer(EMBEDDING_MODEL).max_seq_length - 32` (= 224 content
  tokens for all-MiniLM-L6-v2), 40 token overlap. Read the limit off the
  SentenceTransformer, NOT off its tokenizer: the tokenizer reports
  `model_max_length=512` (the BERT architecture limit) while
  sentence-transformers actually truncates at `max_seq_length=256`, silently,
  with no warning. That mismatch is what made the original 500-token setting
  a real recall hole rather than a cosmetic one — and BM25, which indexes the
  full text, masked it in hybrid results
- Chunk text must be a **verbatim substring of the source document**.
  Window over tokens to pick boundaries, then slice the ORIGINAL string by
  character using the fast tokenizer's `offset_mapping`. Do NOT reconstruct
  chunks with `tokenizer.decode()`: MiniLM's tokenizer has
  `do_lower_case=true` and splits punctuation onto its own tokens, so
  "Dr. Smith reported 5.2% (n=40)" decodes back as
  "dr. smith reported 5. 2 % ( n = 40 )" — and that string is what reaches
  the synthesis prompt and the citation block in the UI
- Each chunk gets a stable `id` built by `schema.make_unit_id()` — never
  hand-formatted. Convention:
  `{domain}_{source_type}_{file_slug}_{file_hash}_{index:04d}`. The
  per-file discriminator is load-bearing, not decoration: chunk indices
  restart at 0 for every DOCX, so without it the second document ingested
  would produce the same IDs as the first and Chroma `.upsert()` would
  silently overwrite it — and documents arrive in pieces, so that is the
  normal case
- `domain` is always `"medical"` for this extractor — hardcoded is fine
  here because this extractor is semantically tied to the medical domain
  (unlike the tabular extractor which is cross-domain)
- Must preserve heading/section structure in `metadata.extra` where possible
  (e.g. `{"section": "4.2", "document_title": "Vaccine Guidelines"}`)
- Data arrives incrementally — re-running the extractor on a new DOCX
  must add new chunks to the index without corrupting existing ones
  (Chroma's `.upsert()` already handles this — don't replace, upsert)

### Input
File path to a `.docx` file.

### Output
`list[KnowledgeUnit]` — one unit per chunk.

### Placeholder strategy (Phase 3 start, before real medical data arrives)
Use 3–5 publicly available medical guideline PDFs converted to DOCX, or
any structured DOCX document. The extractor code doesn't need real
medical content to be built and tested — it just needs text to chunk.
When real DOCX files arrive from other students, swap the input folder,
zero code changes.

---

## Agent 6 — Tabular Extractor Agent (evolved from Narrative Generator)

**Status:** ⚠️ Core logic built (Phase 0), needs Phase 2 upgrade
**File (planned):** `src/extractors/tabular_extractor.py`
**Wraps:** `src/loader.py` + `src/narrative_generator.py`

### Role
Ingests any CSV or Excel file (financial watchlist, medical experiment
CSV, or any future tabular dataset), generates one narrative story per
row via the Narrative Generator Agent, and wraps each story as a
`KnowledgeUnit` — tagged with the caller-supplied domain.

### Key design point — why this is cross-domain
Medical data includes CSVs (tcell antigen dataset, filtered human-subject
dataset). Financial data is also CSV/Excel. The SAME extractor handles
both because format (tabular) and domain (medical/financial) are
independent axes. Domain is a parameter passed by the caller — never
inferred by the extractor itself. This is what makes the system
genuinely format-agnostic.

### Constraints
- Zero hardcoded column names, sheet names, or field assumptions — must
  handle any tabular schema without code changes (already proven against
  stocks CSV and coffee products CSV in Phase 0)
- `domain` is a REQUIRED parameter — raise an error if not supplied, never
  default to either domain
- `source_type` is always `"tabular"` — hardcoded is correct here
- Each unit's `id` is built by `schema.make_unit_id()` — never
  hand-formatted. Same per-file discriminator as the text extractor, and
  here the collision is guaranteed rather than merely likely: the tcell
  antigen CSV and the filtered human-subject CSV are BOTH
  `domain="medical"`, so a per-file row counter gives both a row 0 of
  `medical_tabular_0000`
- Same incremental ingestion requirement as the text extractor: upsert,
  never replace

### What Phase 2 adds (over the current Phase 0 build)
1. Wraps output in `KnowledgeUnit` instead of the current ad-hoc dict
2. Adds `domain` as a required parameter
3. Moves to `src/extractors/tabular_extractor.py` (currently lives
   inline in `narrative_generator.py` + `main.py`)

### Input
- `file_path: str` — path to CSV or Excel file
- `domain: Literal["medical", "financial"]` — must be provided by caller

### Output
`list[KnowledgeUnit]` — one unit per row.

---

*End of AGENTS.md. Add a new section here for every new agent introduced,
and update status markers as phases complete.*