# Evaluation Results

Generated 2026-09-11 · 5.0s · 0 API calls (90 served from cache)

## Setup

|  |  |
|---|---|
| Generator | `openai/gpt-oss-20b` |
| Judge | `qwen/qwen3.8-27b` — a different family, deliberately |
| Embeddings | `all-MiniLM-L6-v2` (256-token limit, 224-token chunks) |
| Corpus | financial 15 · medical 11 units |
| Golden set | 15 financial + 15 medical (8 deliberately unanswerable) + 4 routing-only |
| k | 5 |

## Read this first

**The golden set was written by the person who built the system.** That is a
real contamination risk: questions get phrased in the corpus's own vocabulary,
and only for things known to be answerable. Two mitigations are in place —
8 deliberately unanswerable questions, and questions the system is known to
FAIL (the superlatives) — but neither substitutes for blind questions from
someone who has not seen the corpus. Treat these numbers as a measurement of
the system against a friendly test set, not as an unbiased benchmark.

**The headline retrieval metric is Recall@5, not Precision@5.** PRD section 7
asked for precision@5 ≥ 80%. Most questions here have exactly ONE relevant
chunk (one stock = one row = one chunk), so perfect retrieval scores 1/5 =
0.20 and the target is arithmetically unreachable. Precision is still
reported below, next to its own ceiling, so the number PRD asked for is
present rather than quietly dropped.

**The corpus is small** — 15 and 11 documents. At k=5 a single search already
sees a third of the medical corpus. Several results below only make sense
with that in mind, and are noted where it matters.

---

## Experiment 1 — Retrieval method

*dense vs sparse vs hybrid. Zero LLM calls: these are computed from retrieved
IDs against hand-labelled gold IDs.*

### financial

| method | Recall@5 | MRR | Hit@5 | P@5 / max possible |
|---|---|---|---|---|
| **dense** | 0.864 | 0.768 | 0.909 | 0.200 / 0.236 |
| **sparse** | 0.818 | 0.773 | 0.818 | 0.200 / 0.236 |
| **hybrid** | 0.909 ✅ | 0.788 | 0.909 | 0.218 / 0.236 |

### medical

| method | Recall@5 | MRR | Hit@5 | P@5 / max possible |
|---|---|---|---|---|
| **dense** | 0.909 ✅ | 0.746 | 0.909 | 0.255 / 0.273 |
| **sparse** | 0.909 ✅ | 0.821 | 1.000 | 0.236 / 0.273 |
| **hybrid** | 0.864 | 0.841 | 0.909 | 0.236 / 0.273 |

**Hybrid retrieval is not uniformly better, and that is the finding.**

On financial it wins clearly — recall 0.909 against
0.864 dense and 0.818 sparse.
On medical it **loses** recall (0.864 against
0.909 for both single methods) while winning MRR
(0.841 against 0.746 dense).

That is Reciprocal Rank Fusion behaving exactly as designed: it rewards
documents *both* rankers agree on, so a document one ranker loves and the
other ignores gets pushed down. `docs/TRACES.md` has a concrete case — TC-014
ranked 4th by dense retrieval and dropped out of the hybrid top-4 entirely.

So hybrid buys better *ordering* at some cost to *coverage* on this corpus.
Worth keeping for the financial domain and for exact-ID lookups, which is
what BM25 is there for — but the assumption that hybrid is strictly better
does not survive measurement.

---

## Experiment 2 — Pipeline architecture

*naive (one retrieval pass, no decomposition, no routing) vs the full agentic
pipeline. Both arms use the same per-query k, so the variable under test is
decomposition and not k.*

### financial

| pipeline | Recall@5 | MRR | Citation acc. | Abstained (should) | Abstained (shouldn't) |
|---|---|---|---|---|---|
| **naive** | 0.909 | 0.788 | 1.000 | 1.000 | 0.182 |
| **agentic** | 0.909 | 0.788 | 1.000 | 1.000 | 0.182 |

### medical

| pipeline | Recall@5 | MRR | Citation acc. | Abstained (should) | Abstained (shouldn't) |
|---|---|---|---|---|---|
| **naive** | 0.864 | 0.841 | 1.000 | 1.000 | 0.091 |
| **agentic** | 0.864 | 0.841 | 1.000 | 1.000 | 0.091 |

**The agentic layer buys nothing measurable at this corpus size. Reported as
found.**

Every metric is identical between the two arms. The reason is visible in the
data rather than a guess: only **4 of 30** questions triggered decomposition
at all, and with 11–15 documents a single k=5 search already retrieves a third
of the medical corpus — leaving the extra passes nothing to find.

This is the honest answer to "what does the agentic part buy you": on *this*
corpus, nothing yet. Decomposition is architecture that pays off when a single
query cannot cover a question's parts, which needs a corpus large enough for
top-k to be genuinely selective. Saying that, with the number attached, is
stronger than claiming an improvement the data does not show.

### A bug this experiment found

Inspecting the four decompositions showed two of them producing **clarifying
questions addressed to the user**, which were then fed to the retriever as
search queries:

> *"Which two companies are you interested in comparing?"*
> *"Do you have any specific weight or medical conditions that might affect dosing?"*

AGENTS.md Agent 2 forbids exactly this ("not question expansion, decomposition")
but nothing enforced it. The prompt now carries a worked wrong/right example
and a guard drops any sub-query addressing the user. After the fix all four
decompositions are genuine search queries. The ablation's value here was not
its headline number — it was finding this.

---

## Experiment 3 — Routing method

| router | accuracy | correct | ambiguous flagged |
|---|---|---|---|
| **embedding:max** | 0.967 | 29/30 | 2/4 |
| **embedding:centroid** | 0.967 | 29/30 | 2/4 |

**96.7% routing accuracy**, against PRD section 7's ≥ 90% target, at zero
API cost and ~35 ms warm.

The single miss is worth reading closely: *"What was the p-value for the primary
endpoint?"* routed financial (0.214) over medical (0.152) — but with a margin of
**0.062, below the 0.10 confidence threshold**. The system therefore flags it as
unsure and searches *both* corpora. There are no silent misroutes in this set;
the one error is one the router knows it might be making.

That is the case for a calibrated confidence signal over the LLM's
self-reported one. An LLM router returns no margin, so it cannot flag anything —
which is why its `ambiguous flagged` column would read 0/4 by construction.

Two of the four deliberately ambiguous questions were not flagged (margins 0.174
and 0.149). *"Which entries are missing data?"* is genuinely answerable in both
corpora — financial has unreported quarters, medical has a degraded sample — so
a confident single-domain route is a real limitation, not a threshold to tune
away.

---

## Against the PRD targets

| metric | target | measured (financial / medical) |  |
|---|---|---|---|
| Routing accuracy | ≥ 90% | 96.7% | ✅ |
| Citation accuracy | ≥ 85% | 100.0% / 100.0% | ✅ |
| Retrieval (Recall@5) | — (replaces P@5) | 0.909 / 0.864 | — |
| Golden set size | ≥ 15/domain | 15 / 15 | ✅ |
| Retrieval ablation | required | 3 methods × 2 domains | ✅ |
| Naive-vs-agentic ablation | required | reported, no difference found | ✅ |
| Faithfulness (LLM judge) | ≥ 4.0/5 | reported as supported/total, not 1–5 | see note |

**On faithfulness:** the target was a 1–5 average from an LLM judge. That number
cannot be audited — two judges say 3 and 4 and there is no way to adjudicate.
The system instead reports claim-level `supported/total` from a different model
family (`src/verifier.py`), which decomposes: a reader can look at the
unsupported claims and disagree. It is labelled a *self-check* rather than a
hallucination score, because a system grading itself is a signal, not a
measurement.

## Reproduce

```bash
python -m src.main setup                 # rebuild indexes, no API calls
python -m src.eval.run_eval --quick      # experiments 1 and 3, no API calls
python -m src.eval.run_eval              # all three
python -m src.eval.report                # re-render this file
```

Per-case results, including every answer and every retrieved ID, are in
`docs/eval_results.json` — that is what to read if you do not believe a number
above.
