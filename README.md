# Agentic AI Powered Retrieval-Augmented Generation System

A data-agnostic RAG pipeline: any tabular dataset (CSV/Excel) is turned into
narrative story documents, indexed with hybrid search (dense + BM25), and
queried through an agentic layer that decomposes complex questions before
retrieving.

Two sample datasets are included to prove the pipeline is not hardcoded to
one domain:
- `data/sample_stocks.csv` — 15 real rows pulled from the watchlist/quarterly
  results sheet
- `data/sample_products.csv` — 12 rows of an unrelated coffee shop product
  catalog

---

## 1. Setup (run once)

Open this folder in VS Code, then open a terminal (`` Ctrl+` ``) and run:

```bash
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copy the env file and add your OpenAI key:

```bash
cp .env.example .env
```

Open `.env` in VS Code and replace `sk-your-key-here` with your real
OpenAI API key (get one at platform.openai.com if you don't have one).

---

## 2. Run it on the stock data

Three steps: ingest (generate narratives) → index (build hybrid search) → ask.

```bash
python -m src.main ingest --data data/sample_stocks.csv --dataset-name stocks
python -m src.main index --dataset-name stocks
python -m src.main ask --dataset-name stocks --question "Which stocks are tied to auto production and how did they perform this quarter?"
```

Try a second, more complex question to see the agentic decomposition kick in:

```bash
python -m src.main ask --dataset-name stocks --question "Compare the profit growth of auto-linked stocks against power/energy-linked stocks this quarter"
```

---

## 3. Prove it's data-agnostic — swap the dataset, zero code changes

```bash
python -m src.main ingest --data data/sample_products.csv --dataset-name products
python -m src.main index --dataset-name products
python -m src.main ask --dataset-name products --question "Which products are growing fastest and which are underperforming?"
```

Same three commands, same code, completely different domain. This is the
proof that the ingestion → narrative → retrieval pipeline generalizes.

---

## How it works

```
Any CSV/Excel  ->  Narrative agent  ->  Story corpus  ->  Hybrid index (BM25 + dense)
                                                                |
User question  ->  Query planner agent (decomposes if complex) |
                                     |                          |
                                     v                          v
                              Retrieval across sub-queries -----+
                                     |
                                     v
                         Synthesis agent -> cited answer
```

- **`src/loader.py`** — generic tabular loader, no hardcoded schema
- **`src/narrative_generator.py`** — LLM turns each row into a story (the
  automated version of the excel → Gemini workflow)
- **`src/build_index.py`** — builds a Chroma (dense) index and a BM25
  (sparse) index over the generated stories
- **`src/hybrid_retrieval.py`** — fuses dense + sparse results with
  Reciprocal Rank Fusion
- **`src/agent.py`** — the agentic layer: decomposes complex questions,
  retrieves per sub-query, synthesizes one grounded answer with citations
- **`src/main.py`** — CLI entrypoint (`ingest`, `index`, `ask`)

## Next steps (not yet built — for the full 45-day project)

- Eval harness: hand-labelled Q&A pairs, faithfulness + citation accuracy scoring
- FastAPI wrapper around `src/agent.py` for a real API endpoint
- Streamlit dashboard for a visual query interface
- Docker packaging
- Quarterly re-ingestion so the corpus grows over time
