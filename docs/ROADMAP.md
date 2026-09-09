# Build Roadmap — 40 Days (Multi-Domain, Multi-Format)

Reference PRD.md and TRD.md before starting each phase. Each phase lists:
**Why → Where (files touched) → When (days) → How (tasks)**.

Schema comes first, deliberately — everything else depends on it.

---

## Phase 0 — Already done ✅

- Financial/tabular pipeline: loader, narrative generator, hybrid index,
  agentic query/synthesis, CLI — built and tested on 2 datasets.

---

## Phase 1 — Lock the Knowledge Unit schema (Days 1–3)

- **Why:** both extractors must output an identical shape, or every
  downstream module (indexing, retrieval, agent) needs domain-specific
  branching — exactly what we're trying to avoid.
- **Where:** `src/schema.py`, `docs/TRD.md` §3
- **When:** Days 1–3
- **How:**
  1. Define the Knowledge Unit as a Pydantic model — enforces the shape at
     runtime, not just in docs
  2. Write 2 example instances by hand (one medical, one financial) to
     sanity-check the schema covers both domains' real metadata needs
  3. Do not proceed to Phase 2/3 until this is stable

---

## Phase 2 — Tabular extractor agent — financial AND medical (Days 4–9)

- **Why:** confirmed the tabular extractor is not financial-only — medical
  data includes CSV too (tcell antigen dataset, filtered human-subject
  dataset). Building and testing it against two unrelated domains now,
  rather than one, is what actually proves schema-agnosticism.
- **Where:** `src/extractors/tabular_extractor.py` (wraps existing
  `loader.py` + `narrative_generator.py`, adds a `domain` parameter)
- **When:** Days 4–9
- **How:**
  1. Wrap existing narrative generation output into Knowledge Unit shape;
     `domain` is now a required argument, not hardcoded to `"financial"`
  2. Re-run against `sample_stocks.csv` and `sample_products.csv` with
     `domain="financial"` — confirm no regression
  3. Run the same code against the tcell antigen CSV and the filtered
     human-subject CSV with `domain="medical"` as soon as they're
     available — if delivery is delayed, this step slips but the code
     shouldn't need to change when it arrives
  4. Confirm schema-agnosticism holds across genuinely different column
     sets (stock tickers vs. antigen/experiment fields) — this is a much
     stronger test than the earlier stocks-vs-coffee-products proof

*Can run in parallel with Phase 3 if using a multi-agent coding tool — they
don't share state.*

---

## Phase 3 — Text extractor agent (medical DOCX) (Days 10–16)

- **Why:** the second of the two modules sir explicitly asked for.
  Confirmed real format is DOCX, not PDF.
- **Where:** `src/extractors/text_extractor.py` (chunking logic lives here,
  not a separate `chunker.py` — small enough to stay in one file; update
  from the original plan)
- **When:** Days 10–16
- **How:**
  1. Implement `docx_loader` (python-docx) — extract text per paragraph,
     preserve heading structure where possible
  2. Chunk by real tokens (~500 tokens, ~50 overlap), measured with the
     SAME tokenizer the embedding model uses at index time
     (`SentenceTransformer(EMBEDDING_MODEL).tokenizer` — no new
     dependency, sentence-transformers already ships it). Originally
     planned as a word-count approximation; upgraded once we realized the
     real tokenizer was a free swap
  3. Wrap output into Knowledge Unit shape, `domain="medical"`,
     `source_type="textual"`
  4. Medical DOCX documents arrive in pieces — test with whatever's
     available first, confirm re-running ingestion later just adds more
     without breaking what's already indexed (Chroma upsert already
     supports this)
  5. PDF support: skip entirely for MVP. Only revisit if all other phases
     are done early and a real PDF document actually shows up

---

## Phase 4 — Domain-tagged hybrid indexing (Days 17–20)

- **Why:** separate collections prevent medical and financial content from
  polluting each other's retrieval results.
- **Where:** `src/build_index.py` (modified to accept a `domain` param)
- **When:** Days 17–20
- **How:**
  1. Modify `build_index.py` to build `medical_collection` and
     `financial_collection` as separate Chroma collections + separate BM25
     pickles
  2. Index both domains' Knowledge Units
  3. Sanity check: query each collection directly (bypassing the router)
     to confirm retrieval quality per domain before adding routing on top

---

## Phase 5 — Domain router agent (Days 21–24)

- **Why:** confirmed direction — auto-detect domain, no manual selection.
- **Where:** `src/domain_router.py`, `src/agent.py` (modified to call the
  router before retrieval)
- **When:** Days 21–24
- **How:**
  1. Implement structured-output classification (`instructor` + Pydantic)
     returning `{domain, confidence}`
  2. Wire into `agent.py`: router runs first, then existing query planner
     + hybrid retrieval + synthesis run against the routed collection
  3. Test with obviously-medical, obviously-financial, and a few
     deliberately ambiguous questions

---

## Phase 6 — Eval harness (Days 25–32)

- **Why:** PRD §7 success metrics; RULES §3 non-negotiable #6.
- **Where:** `src/eval/golden_dataset_medical.json`,
  `src/eval/golden_dataset_financial.json`, `src/eval/run_eval.py`,
  `src/eval/metrics.py`
- **When:** Days 25–32
- **How:**
  1. Hand-write ≥ 15 Q&A pairs per domain (30 total minimum; aim for 25/
     domain, 50 total, if time allows — see PRD §7). Ask sir or one other
     student to contribute a few questions blind, without seeing the
     system first, to reduce self-authored eval bias
  2. Include a handful of intentionally ambiguous questions specifically
     to measure domain routing accuracy
  3. Implement faithfulness scoring, citation accuracy, retrieval
     precision@5 — reuse logic across domains, run twice
  4. Faithfulness judge uses a DIFFERENT model than the one generating
     answers — grading your own answers with the same model that wrote
     them is a biased judge and won't hold up under questioning
  5. **Retrieval ablation:** run the same golden set through
     `dense_search()` alone, `sparse_search()` alone, and `hybrid_search()`
     — report precision@5 for each. Both standalone functions already
     exist in `hybrid_retrieval.py`, so this is close to free. Proves
     hybrid retrieval earns its complexity instead of assuming it
  6. **Naive-vs-agentic ablation:** add a bypass path that skips
     `decompose_query()` and domain routing — single hybrid search +
     `synthesize_answer()` only — and run the same golden set through it.
     Compare its accuracy against the full pipeline. This is the number
     that actually answers "what does the agentic part buy you," not just
     the architecture diagram
  7. Ablations 5 and 6 test different variables (retrieval method vs.
     pipeline architecture) on the same golden set — report them as two
     separate, clearly-labeled experiments, not one combined table, so
     the result reads as controlled experimentation rather than a wall of
     numbers
  8. Save results to `docs/EVAL_RESULTS.md`, broken out per domain — this
     is your resume bullet source

---

## Phase 7 — Backend + deployment (Days 33–36)

- **Why:** TRD §6 API contract; portfolio link requirement.
- **Where:** `src/api/main_api.py`
- **When:** Days 33–36
- **How:**
  1. Wrap `extract`, `index`, `ask`, `eval/run` as endpoints per TRD §6
  2. Deploy to Render; move API keys to environment variables
  3. **If behind schedule:** collapse to a single Streamlit app calling
     pipeline functions directly, skip the separate FastAPI deployment —
     note the trade-off honestly in the README

---

## Phase 8 — Streamlit dashboard + polish (Days 37–40)

- **Why:** UI last, as planned; final packaging for viva + portfolio.
- **Where:** `app/streamlit_app.py`, `README.md`
- **When:** Days 37–40
- **How:**
  1. Tab 1 — Upload: DOCX only for now (medical); shows which domain it
     was tagged as
  2. Tab 2 — Agentic chat: shows the routed domain, decomposed
     sub-questions, retrieved sources, cited answer
  3. Access-code gate before any API calls
  4. Deploy frontend to Streamlit Community Cloud
  5. Update README with final architecture, both domains' eval numbers,
     deployed link
  6. Rehearse viva answers for: "why domain routing instead of searching
     everything," "why a shared schema," "what happens if routing gets it
     wrong"

---

## Time budget summary

| Phase | Days | Cumulative |
|-------|------|------------|
| 1 — Knowledge Unit schema | 3 | 3 |
| 2 — Tabular extractor | 6 | 9 |
| 3 — Text extractor | 7 | 16 |
| 4 — Domain-tagged indexing | 4 | 20 |
| 5 — Domain router agent | 4 | 24 |
| 6 — Eval harness | 8 | 32 |
| 7 — Backend + deployment | 4 | 36 |
| 8 — UI + polish | 4 | 40 |

Phases 2 and 3 can run in parallel if using a multi-agent coding tool,
since neither depends on the other's output — only on the Phase 1 schema.
That would compress the critical path to roughly 34 days, leaving slack for
the inevitable slippage in eval-harness hand-labeling (Phase 6 is the
phase most likely to run long).

**Phase 6 scope grew** (2 ablation studies added, see above) — still
budgeted at 8 days for now since both ablations reuse existing retrieval
and pipeline functions rather than building new ones, but this is the
most likely place the 8-day estimate slips. Watch Groq rate limits too:
ablations roughly double-to-triple the number of eval-set passes, which
means more API calls per eval run than originally planned.