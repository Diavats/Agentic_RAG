# PRISM: one RAG pipeline, two domains, two formats

Ask plain-English questions about **finance** and **medical** documents and get
answers that cite the exact passage they came from. Word-document prose and
spreadsheet rows go through the *same* pipeline: nothing downstream knows or
cares which format or domain a passage came from.

| | |
|---|---|
| **Live app** | https://prism-ten-red.vercel.app |
| **Live API** | https://prism-api-y5op.onrender.com/docs |
| **Eval report** | [`docs/EVAL_RESULTS.md`](docs/EVAL_RESULTS.md) |
| **Real runs, failures included** | [`docs/TRACES.md`](docs/TRACES.md) |

> The free backend sleeps after 15 minutes idle. The first visit takes about a
> minute to wake it; the app shows "Waking up the server…" while it does.

BTech final-year project. Built in 40 days, aimed at a viva panel and a technical screen.

---

## What makes it more than "a RAG chatbot"

| Claim | Evidence |
|---|---|
| **Hybrid retrieval, measured.** Dense (MiniLM) + sparse (BM25), fused with Reciprocal Rank Fusion | Ablation in `EVAL_RESULTS.md`: hybrid gives the best ranking (MRR) in both domains, but **not** always the best recall. Reported as measured |
| **One schema, two formats.** DOCX chunks and CSV/Excel rows both become a `KnowledgeUnit` | `src/schema.py`; a single question is answered from a Word doc **and** a spreadsheet row together (TRACES.md) |
| **The router decides the domain**, with no LLM call | 29/30 on the golden set, about 15 ms; ambiguous questions search both domains instead of guessing |
| **Every step is visible.** Route → plan → retrieve → answer → verify, streamed live | `/ask/stream` (server-sent events). Measured in a real browser: steps arrive at 5.0s, 5.9s, 10.3s, 11.2s, i.e. truly progressive |
| **An evaluation designed to be hard to fool** | Golden set, 3 ablations, a judge from a **different vendor** than the generator, and 10 **blind** questions from people who never saw the corpus (`src/eval/blind_questions.txt`, committed before any run) |
| **Honest numbers** | "Naive == agentic" on this test set is reported because it is true. Known failures (superlatives) are documented, not hidden |

---

## Architecture

```
 Word (.docx) ──► text extractor ─┐                       ┌── dense (Chroma, MiniLM)
                                  ├─► KnowledgeUnit ──► index ─┤
 CSV / Excel ───► tabular extractor┘   (one schema)        └── sparse (BM25)
                  (LLM writes a narrative per row)

 Question ─► router (cosine margin) ─► planner (split if multi-part)
          ─► hybrid search per sub-query (RRF fusion) ─► synthesis with [S1] citations
          ─► verifier (different-vendor judge, claim by claim) ─► answer + trace
```

| Layer | Tech | Why |
|---|---|---|
| Generator | `openai/gpt-oss-20b` on Groq | Free tier, fast |
| Judge | `qwen/qwen3.8-27b` | Different company than the generator, so it isn't grading its own team |
| Embeddings | `all-MiniLM-L6-v2` (local, CPU) | Free; chunk size is **derived** from its 256-token limit |
| Vector store | Chroma (rebuilt from committed units at startup) | The index is derived data; the units are the source of truth |
| Backend | FastAPI on Render (free) | Streaming, upload sandbox, per-visitor quota |
| Frontend | Next.js 16 + Tailwind on Vercel | Auto-deploys on every push to `main` |

### The app (frontend/)

| Page | What it does |
|---|---|
| **Welcome** | Prismo, the prism mascot, explains PRISM; sample questions you can tap |
| **Chat** | Each answer is an "album page": five numbered slots fill in as the stream arrives; source stickers open the exact passage. A **Files** drawer accepts your own CSV/Excel/Word file (finance or medical only, checked first) |
| **How it works** | Replays one **real recorded** question on a star chart; star size = real retrieval score |
| **Benchmarks** | Live numbers from `GET /benchmark`, with plain-language notes |

Design decisions: [`docs/adr/ADR-001-chat-frontend.md`](docs/adr/ADR-001-chat-frontend.md), [`DESIGN.md`](DESIGN.md), [`PRODUCT.md`](PRODUCT.md).

---

## Results (from `docs/eval_results.json`)

Recall@5 / MRR, 11 answerable questions per domain:

| | dense | sparse | **hybrid** |
|---|---|---|---|
| Finance | 0.909 / 0.864 | 1.000 / 0.871 | 0.909 / **0.909** |
| Medical | 1.000 / 0.818 | 0.955 / 0.814 | 0.955 / **0.859** |

- With n=11, **one question moves recall by about 0.09**, so small gaps are within noise. The per-case data shows each domain's gap between methods is a single question.
- Router: 29/30 correct. Citation accuracy 1.000. Abstention on unanswerable questions 1.000.
- The judge has **not** been validated against human grading. Treat its scores as indicative.

---

## Run it locally

```bash
python -m venv venv
venv\Scripts\activate                       # Windows (source venv/bin/activate elsewhere)
pip install -r requirements.txt
copy .env.example .env                       # then add your Groq key (console.groq.com)

venv/Scripts/python.exe -m src.main setup                 # build indexes: zero API calls
venv/Scripts/python.exe -m src.main ask --question "What are the exclusion criteria?"
venv/Scripts/python.exe -m pytest                         # ~1 min, zero API calls
venv/Scripts/python.exe -m src.eval.run_eval --quick      # retrieval + router ablations, free
venv/Scripts/python.exe -m uvicorn src.api.main_api:app --port 8077

cd frontend && npm install && npm run dev                 # app on http://localhost:3000
```

The frontend talks to the live Render API by default. To use a local backend,
put `NEXT_PUBLIC_API_URL=http://localhost:8077` in `frontend/.env.local`.

---

## Security and limits

| Protection | How |
|---|---|
| Daily quota per visitor: 15 questions, 3 uploads, 10 sessions, 20 file checks | Keyed on Cloudflare's `CF-Connecting-IP`, which visitors can't forge |
| Uploads land in a private per-session collection, never the evaluated corpora | `src/api/sessions.py` |
| Off-topic files refused before any LLM call | Embedding gate, threshold 0.20, calibrated in ADR-001 |
| 25-row cap on spreadsheets (one LLM call per row), 2 MB cap, zip-bomb check, safe filenames | `src/api/sessions.py`, `src/api/main_api.py` |
| Answers rendered without raw HTML | react-markdown, no `dangerouslySetInnerHTML` |

## Known limitations

- **"Which is the highest?" questions are unreliable.** Retrieval fetches the closest passages, not every row.
- **The test set is small** (11 answerable per domain) and was written by the builder; the blind set exists to counter this.
- **The medical data is a placeholder** until the real datasets arrive.
- **Free-tier hosting.** About 1 min cold start; uploads and quotas reset when the server restarts.

## Future scope

| Next step | Why |
|---|---|
| A structured-query path (pandas/SQL) for superlatives and aggregates | Fixes the main known failure |
| Score the 10 blind questions; grow the golden set past n=11 | Tighter numbers, less builder bias |
| Validate the judge against human grading | Turns judge scores from indicative into evidence |
| Real medical datasets; re-measure the 0.20 upload threshold | Placeholder data today |
| Redis for quota and sessions; paid instance | Survive restarts; no cold start |
| A reranker after RRF; PDF support | Better ranking; the most common real-world format |

## Repository map

```
src/            pipeline: schema, extractors, index, router, agent, verifier, CLI
src/api/        FastAPI app + upload sandbox
src/eval/       golden sets, blind questions, eval harness, report renderer
frontend/       Next.js app (Vercel)
data/           source files + committed units (data/generated/*_units.json)
docs/           PRD, TRD, AGENTS, ROADMAP, ADRs, EVAL_RESULTS, TRACES, FRONTEND_RULES
tests/          305 offline tests (live ones marked @pytest.mark.live)
CLAUDE.md       working rules, lessons learned, constraints
```
