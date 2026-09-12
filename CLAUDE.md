# CLAUDE.md — working rules for this repository

PRISM: one RAG pipeline serving two domains (medical, financial) across two
formats (DOCX prose, CSV/Excel rows). BTech final-year project, 40-day budget,
targeted at a viva panel *and* a Fortune 500 technical screen.

Read `docs/PRD.md`, `docs/TRD.md`, `docs/AGENTS.md`, `docs/ROADMAP.md` before
changing architecture. This file is the working agreement on top of them.

---

## 1. How to communicate with Dia

- **Never write explanation documents for her.** She asked for this explicitly.
  When she says "show me what you did", give **exact terminal commands to paste
  plus the real output**, because she is showing a mentor. Run every command
  first and quote the actual output — never a plausible-looking one.
- Project artifacts (`docs/TRACES.md`, `docs/EVAL_RESULTS.md`, `README.md`) are
  different: those are for recruiters and the panel, and are wanted.
- Visual, scannable: tables, short bullets. No long paragraphs.
- Give a recommendation, not a menu — but be honest about real trade-offs.
- She is the one who must defend every decision in a viva. Any non-obvious
  choice needs a one-line *why* she can repeat.

---

## 2. The rule that has caught the most bugs

**Run it. Then look at the output.**

Every serious bug in this project was invisible in the code and obvious in the
output. Several were found only after a test *passed*:

- BM25 scored **0.0000 against every document** — `assert target in results`
  passed because with all-zero scores `sorted()` returns insertion order and
  the target happened to be index 0. **Assert on scores, not membership.**
- The eval's first run said "agentic is worse". Inspecting the per-case data
  showed all three differing cases used *one* sub-query — the difference was a
  `k=5` vs `k=4` confound in my own harness.
- Streaming "worked" — every stage arrived at 1.9s together, i.e. not
  streaming at all. Only the timestamps revealed it.

**An ablation with a striking result gets its per-case data inspected before
it goes anywhere near a report.**

---

## 3. Non-negotiables

| # | Rule | Why |
|---|---|---|
| 1 | Both extractors emit `KnowledgeUnit` and nothing downstream branches on domain or format | This is the architectural claim; breaking it makes a third domain a rewrite |
| 2 | Build IDs with `schema.make_unit_id()`, never by hand | Per-file counters made the second CSV silently erase the first on upsert |
| 3 | Chunk size is **derived** from the embedding model, never hardcoded | 500-token chunks into a 256-token model truncated silently |
| 4 | Chunk text is a verbatim substring of the source | `tokenizer.decode()` lowercases and mangles punctuation; that text becomes a citation |
| 5 | The judge model must be a different **vendor** from the generator | A model grading itself is a biased judge. `gpt-oss-120b` is a sibling, not independence |
| 6 | Confidence comes from cosine margin, never an LLM's self-report | An LLM says 0.95 for everything including its mistakes |
| 7 | Uploads land in per-session collections, never the curated corpora | The evaluated system must stay the deployed system |
| 8 | The row cap is enforced **before** any LLM call | One call per row; it is the only thing between a visitor and the daily quota |
| 9 | Every LLM call goes through `llm_cache.cached_completion` | A test asserts no module bypasses it |
| 10 | Report numbers as measured, including bad ones | "naive == agentic" is in the results because it is true |

---

## 4. Things that will bite you

- **Windows cp1252.** LLMs emit em dashes and non-breaking hyphens constantly.
  Any new entry point must force UTF-8 on stdout/stderr.
- **Unicode typography in retrieval.** The narrative generator writes `TC‑014`
  with U+2011. Normalize before tokenizing, identically at index and query time.
- **Citation brackets.** The model writes `【S1】` about a third of the time.
  Parse what it writes, not what it was asked to write.
- **Cold start is ~19.8s vs 37ms warm.** Never average them. Preload in the
  FastAPI lifespan.
- **pandas `NaT` IS a `datetime`.** It passes `isinstance` and `.isoformat()`
  returns the string `"NaT"`.
- **BM25 IDF is exactly 0** for a term in 1 of 2 documents. Small test fixtures
  produce misleading zeros; use 8+ documents.
- **`str.replace` in edit scripts fails silently.** Always `assert count == 1`.
  Two no-ops shipped a `--router` flag that was accepted and ignored, and one
  wrote a literal backspace character into a regex.
- **Read pytest's summary line.** Counting `F` characters miscounts, because
  traceback lines start with `F`.

---

## 5. Cost discipline

Groq free tier has a per-day cap, and Phase 6 needs it.

- Tabular extraction is **one API call per row**. Never re-extract to fix a
  downstream bug — units are persisted in `data/generated/*_units.json`.
- The index is **derived data**: rebuilt from units with zero API calls
  (`python -m src.main setup`). It is not in version control, because Chroma
  writes to its files on *read*.
- The default test suite makes **zero** API calls. Live tests are marked
  `@pytest.mark.live`.

---

## 6. Commands

```bash
venv/Scripts/python.exe -m src.main setup                    # rebuild indexes, no API calls
venv/Scripts/python.exe -m src.main ask --question "..."     # router picks the domain
venv/Scripts/python.exe -m pytest                            # ~90s, zero API calls
venv/Scripts/python.exe -m src.eval.run_eval --quick         # experiments 1 and 3, free
venv/Scripts/python.exe -m src.eval.run_eval                 # all three (cached)
venv/Scripts/python.exe -m uvicorn src.api.main_api:app --port 8077
```

---

## 7. Two things only Dia can do

Flag these; do not attempt them.

1. **Blind eval questions.** If I write them they are not blind — that is the
   entire mechanism. 5 from her mentor, 5 from a classmate.
2. **Judge–human agreement.** She hand-scores 10 eval cases and reports
   agreement with the judge. One hour, and it is the cheapest credibility
   purchase in the project.

Both have human latency. Start them early, in parallel with building.

---

## 8. Git

Commit per phase, push after each. Commit messages record **what was measured
and what was wrong**, not just what changed — they are part of the evidence a
recruiter reads. `.env` is never committed.
