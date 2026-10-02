# CLAUDE.md: working rules for this repository

PRISM: one RAG pipeline serving two domains (medical, financial) across two
formats (DOCX prose, CSV/Excel rows), with a chat frontend. BTech final-year
project, 40-day budget, aimed at a viva panel *and* a technical screen.

Read before changing architecture: `docs/PRD.md`, `docs/TRD.md`,
`docs/AGENTS.md`, `docs/ROADMAP.md`, `docs/adr/`. Frontend: `PRODUCT.md`,
`DESIGN.md`, `docs/FRONTEND_RULES.md`. This file is the working agreement on top.

---

## 0. Where things stand

| Part | Status | Where |
|---|---|---|
| Pipeline (phases 1–6) | Done | `src/` |
| Eval harness + report | Done; blind questions collected, not yet scored | `src/eval/`, `docs/EVAL_RESULTS.md` |
| Backend (phase 7) | Live, auto-deploys on push | Render: https://prism-api-y5op.onrender.com |
| Frontend (phase 8) | Live, auto-deploys on push | Vercel: https://prism-ten-red.vercel.app |
| Judge–human agreement | **Declined by Dia.** Report states the judge is unvalidated | `docs/EVAL_RESULTS.md` |

---

## 1. How to work with Dia

- **No explanation documents for her.** When she says "show me what you did",
  give exact terminal commands plus the **real** output (run it first; never a
  plausible-looking one). She shows these to her mentor.
- Project artifacts (README, TRACES, EVAL_RESULTS) are for recruiters and the panel, and are wanted.
- Visual and scannable: tables and short bullets; cover why / where / how. No long paragraphs.
- Give a recommendation, not a menu, but state real trade-offs honestly.
- She defends every decision in a viva: each non-obvious choice needs a one-line *why* she can repeat.
- Flag scope creep. When a request conflicts with a non-negotiable (§3) or the
  timeline, say so and propose a translation; don't silently comply.
- Ask before outward-facing actions (connecting accounts, deploying new
  services). She pastes secrets (Groq key) herself; never type them.

---

## 2. The rule that has caught the most bugs

**Run it. Then look at the output.** Every serious bug in this project was
invisible in the code and obvious in the output, and several passed tests.

- An ablation, a striking number, or a "0 API calls" line gets its **per-case
  data** inspected before it goes anywhere near a report.
- UI work is verified in a **real browser with screenshots** (playwright-skill),
  at 1440 and 390 widths. The build passing proves nothing about how it looks.
- Assert on **values**, not membership. A test you haven't seen fail proves nothing.

---

## 3. Non-negotiables

| # | Rule | Why |
|---|---|---|
| 1 | Both extractors emit `KnowledgeUnit`; nothing downstream branches on domain or format | The architectural claim. Breaking it makes a third domain a rewrite |
| 2 | Build IDs with `schema.make_unit_id()`, never by hand | Per-file counters made a second CSV silently erase the first on upsert |
| 3 | Chunk size is **derived** from the embedding model | 500-token chunks into a 256-token model truncated silently |
| 4 | Chunk text is a verbatim substring of the source | `tokenizer.decode()` lowercases and mangles punctuation, and that text is a citation |
| 5 | The judge is a different **vendor** from the generator | A model grading itself is biased. `gpt-oss-120b` is a sibling, not independence |
| 6 | Confidence comes from cosine margin, never an LLM's self-report | An LLM says 0.95 for everything, including its mistakes |
| 7 | Uploads land in per-session collections, never the curated corpora | The evaluated system must stay the deployed system |
| 8 | Row cap, topic gate and zip check run **before** any LLM call | One call per row; these are all that stand between a visitor and the daily quota |
| 9 | Every LLM call goes through `llm_cache.cached_completion` | A test asserts no module bypasses it |
| 10 | Report numbers as measured, including bad ones | "naive == agentic" is in the results because it is true |
| 11 | Narratives copy every number **verbatim** (no %, no rescaling) | The model mis-scaled 29 of 42 figures; retrieval can't fix a wrong number in the source |
| 12 | Report prose that states a verdict is **computed** from the data | Hardcoded "wins clearly" became false the moment the numbers moved |
| 13 | Visitor identity comes from `CF-Connecting-IP`, never `X-Forwarded-For` | Render appends to XFF, so its first entry is forgeable. Proven bypass, fixed |
| 14 | Extractors stay schema-agnostic: no hardcoded columns or sheets; domain is a parameter | Sir confirmed columns and sheets will change; medical data arrives in pieces |
| 15 | Demonstration data in the UI is real (live API or a labelled recorded trace) | Invented numbers on a benchmark page would undo the whole project |

---

## 4. Things that will bite you

**Data and retrieval**
- **Windows cp1252.** LLMs emit em dashes and non-breaking hyphens. Every entry point forces UTF-8.
- **Unicode typography.** The model writes `TC‑014` (U+2011) and minus as `–` (U+2013). Normalise with `build_index.normalize_for_bm25`, identically at index and query time, and in tests.
- **Citation brackets.** The model writes `【S1】` about a third of the time. Parse what it writes.
- **Cold start ~19.8 s vs 37 ms warm.** Never average them. Preloaded in the FastAPI lifespan.
- **pandas `NaT` is a `datetime`**; `.isoformat()` returns the string `"NaT"`.
- **BM25 IDF is exactly 0** for a term in 1 of 2 docs. Test fixtures need 8+ documents.
- **The index is derived data.** `ensure_index` compares stored text with the units and rebuilds when they differ. Before that fix, re-extraction left the old text indexed and the eval scored stale data.

**Tooling on this machine (Windows, 8 GB RAM)**
- **`str.replace` in edit scripts fails silently.** Always `assert count == 1`.
- **pytest's summary line:** read it; don't count `F`s. `-q` on the command line stacks with the `-q` in `pytest.ini` and hides the summary; use `-o addopts=""`.
- **PowerShell `*>` writes UTF-16 logs.** grep can't read them; pipe through `ForEach-Object { "$_" }` or `Out-File -Encoding utf8`.
- **`venv/Scripts/python.exe` is a launcher** that spawns the real interpreter. Measuring its memory from outside reports ~5 MB. Measure from inside the process.
- **HuggingFace HEAD requests hang on flaky DNS.** Use `HF_HUB_OFFLINE=1` once the model is cached.
- **Low memory.** Don't run two test suites at once (25 min vs 1 min); stop dev servers when done.

**Frontend**
- **Next.js 16 is not the Next.js in training data.** Read `frontend/node_modules/next/dist/docs/` before using an API.
- **Tailwind v4 layering:** custom classes (`.card`, `.btn`, `.sticker`) must sit in `@layer components`, or they silently beat every `bg-*` utility. This rendered the star chart white.
- **Layouts from hashes of similar IDs clump.** Use index-based layouts (golden-angle spiral).
- **Sticky elements on mobile hide content.** Check what an IntersectionObserver band actually shows at 390px.
- **Body background hides `-z-10` layers.** The page colour lives on `<html>`.

---

## 5. Lessons log: what went wrong and the rule it produced

| Mistake | How it was caught | Rule now |
|---|---|---|
| BM25 scored 0.0000 against every document; the test passed anyway | Inspecting scores, not membership | Assert on values |
| Eval said "agentic is worse"; really a `k=5` vs `k=4` confound in the harness | Per-case data | Inspect per-case data before reporting |
| "Streaming" delivered every stage at 1.9 s together | Timestamps per event | Verify streaming with timestamps |
| Narratives mis-scaled 29/42 figures (10.037 → "10.037%") | Auditing the units against the CSV | Non-negotiable 11; `tests/test_narrative_numbers.py` |
| Re-extraction kept stale text in the index; eval reported "0 API calls" | That line was suspicious, so it was checked | `ensure_index` compares content |
| Report prose contradicted its own tables after a re-run | Reading the regenerated report | Non-negotiable 12 |
| Every source reached the API with an empty `source_file` | Live API test | Test the real API, not only units |
| Asking during an upload returned 500 | Live API test | 409 + test |
| Finance Word docs were tagged medical | Design review for uploads | Domain is a parameter (non-negotiable 14) |
| Quota bypass via forged `X-Forwarded-For` | Security review, proven on Render | Non-negotiable 13 + regression test |
| Upload filename path traversal; zip-bomb risk; raw exceptions sent to the browser | Security review | Bare filename, unpacked-size cap, generic messages + server log |
| Frontend colour classes silently overridden | Screenshot review | §4 Tailwind layering |
| Claimed a test result before reading the summary line | Re-running with `-o addopts=""` | Read pytest's summary line |

---

## 6. Cost discipline

Groq free tier has a per-day cap.

- Tabular extraction is **one API call per row**. Re-extract only to fix the extraction itself (e.g. the number-scaling bug), never for a downstream bug. Units are persisted in `data/generated/*_units.json`.
- The index is rebuilt from units with zero API calls (`src.main setup`). It is not in version control (Chroma writes to its files on read).
- The default test suite makes **zero** API calls; live tests are `@pytest.mark.live`.
- A live question from a test script spends the visitor quota and Groq calls; re-verify UI changes without asking unless the change touches answering.

---

## 7. Commands

```bash
venv/Scripts/python.exe -m src.main setup                    # rebuild indexes if units changed; no API calls
venv/Scripts/python.exe -m src.main ask --question "..."     # router picks the domain
venv/Scripts/python.exe -m pytest -o addopts=""              # ~1 min, zero API calls, shows the summary
venv/Scripts/python.exe -m src.eval.run_eval --quick         # experiments 1 and 3, free
venv/Scripts/python.exe -m src.eval.run_eval                 # all three (cached LLM calls)
venv/Scripts/python.exe -m src.eval.report                   # re-render docs/EVAL_RESULTS.md
venv/Scripts/python.exe -m uvicorn src.api.main_api:app --port 8077
cd frontend && npm run dev                                   # http://localhost:3000 (uses the live API)
cd frontend && npm run build                                 # typecheck + production build
```

---

## 8. Deployment

| | Render (backend) | Vercel (frontend) |
|---|---|---|
| Config | `render.yaml` (Blueprint "Prism") | project "prism", root `frontend/` |
| Deploys | On every push to `main` | On every push to `main` |
| Secrets | `GROQ_API_KEY` set by Dia in the dashboard | None (the API URL is public) |
| Limits | Free: 512 MB (measured peak ~362 MB), sleeps after 15 min, ~1 min wake | Free hobby |

- Before a demo, open the app about 2 minutes early to wake the backend.
- A frontend-only push also rebuilds Render (no build filter set yet).

---

## 9. Frontend rules (summary)

- World: **Sticker Album**, neo-brutalist, bubblegum-pink ground (never white), ink outlines, hard offset shadows, white die-cut rim. Tokens and rules: `DESIGN.md`.
- Motion follows Emil Kowalski: `ease-out` curves, under 300 ms for UI, press feedback, hover only on real pointers, everything off under `prefers-reduced-motion`.
- Contrast: muted text at no less than 60% ink.
- Code: no UI kit, no animation library; every block has a one-line plain-English comment.

---

## 10. Things only Dia can do

1. **Blind eval questions:** collected (`src/eval/blind_questions.txt`, committed before any run). Answer labels are added afterwards by the builder, and that is disclosed.
2. **Judge–human agreement:** declined. The report says the judge is unvalidated; never claim otherwise.

---

## 11. Git

Commit per phase, push after each. Commit messages record **what was measured
and what was wrong**, not just what changed; they are evidence a recruiter
reads. `.env` is never committed. Local scratch (`.impeccable/review/`,
`.playwright-mcp/`, logs) is gitignored.

## 12. Future scope

See README "Future scope". Top item: a structured-query path for superlatives and aggregates.
