"""
Evaluation harness — Phase 6.

    python -m src.eval.run_eval              # everything
    python -m src.eval.run_eval --quick      # retrieval + routing only, no LLM calls

Writes docs/EVAL_RESULTS.md (for humans) and docs/eval_results.json (for the
Phase 8 benchmark panel).

--- Three experiments, reported separately ---

1. RETRIEVAL ABLATION  dense vs sparse vs hybrid.
   Costs ZERO LLM calls: recall/MRR are computed from retrieved IDs against
   hand-labelled gold IDs. Re-synthesizing an answer per arm would have cost
   ~180 calls to measure something that is not about answers at all.

2. PIPELINE ABLATION  naive vs agentic.
   Naive = one retrieval pass on the raw question, no decomposition, no
   routing. Agentic = the full pipeline. This is the number that answers
   "what does the agentic layer actually buy you", and it is reported
   whatever it says.

3. ROUTER ABLATION  embedding:max vs embedding:centroid vs llm.

--- On honesty ---

The golden set was authored by the same person who built the system. That is a
real contamination risk: questions get written in the corpus's own vocabulary,
and only for things known to be answerable. Two mitigations are already in
place — unanswerable cases, and questions the system is known to FAIL (the
superlatives) — but neither substitutes for blind questions from someone who
has not seen the corpus. This is stated in the generated report rather than
left for a reader to discover.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from src import llm_cache
from src.agent import ask, synthesize_answer
from src.config import EMBEDDING_MODEL, LLM_MODEL, VERIFIER_MODEL
from src.domain_router import route
from src.eval.metrics import (
    citation_accuracy,
    hit_at_k,
    is_abstention,
    max_precision_at_k,
    mean,
    precision_at_k,
    reciprocal_rank,
    recall_at_k,
)
from src.hybrid_retrieval import dense_search, hybrid_search, sparse_search, warm_up
from src.trace import RetrievedSource, resolve_citations
from src.unit_store import load_units

EVAL_DIR = Path(__file__).parent
K = 5


def load_golden(name: str) -> list[dict]:
    return json.loads((EVAL_DIR / f"golden_{name}.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Experiment 1 — retrieval ablation. No LLM calls.
# --------------------------------------------------------------------------

def run_retrieval_ablation(cases: list[dict]) -> dict:
    methods = {
        "dense": lambda q, d: [i for i, _ in dense_search(q, d, k=K)],
        "sparse": lambda q, d: [i for i, _ in sparse_search(q, d, k=K)],
        "hybrid": lambda q, d: [h["row_id"] for h in hybrid_search(q, d, k=K)],
    }
    answerable = [c for c in cases if c["answerable"]]
    results = {}

    for name, search in methods.items():
        per_case = [(search(c["question"], c["domain"]), c["gold_chunk_ids"])
                    for c in answerable]
        results[name] = {
            "recall@5": mean([recall_at_k(r, g, K) for r, g in per_case]),
            "mrr": mean([reciprocal_rank(r, g) for r, g in per_case]),
            "hit@5": mean([hit_at_k(r, g, K) for r, g in per_case]),
            "precision@5": mean([precision_at_k(r, g, K) for r, g in per_case]),
            "max_possible_precision@5": mean([max_precision_at_k(g, K) for _, g in per_case]),
            "n": len(per_case),
        }
    return results


# --------------------------------------------------------------------------
# Experiment 2 — pipeline ablation. Costs LLM calls (cached).
# --------------------------------------------------------------------------

def run_naive(case: dict) -> dict:
    """Single retrieval pass on the raw question. No routing, no decomposition.

    The domain is handed to it, so the naive arm is not penalised for lacking a
    router — this isolates decomposition, which is the variable under test.
    """
    hits = hybrid_search(case["question"], case["domain"], k=K)
    sources = [
        RetrievedSource(id=h["row_id"], text=h["text"], score=h["score"], rank=i,
                        domain=case["domain"])
        for i, h in enumerate(hits, start=1)
    ]
    answer = synthesize_answer(case["question"], sources)
    return {
        "retrieved_ids": [s.id for s in sources],
        "answer": answer,
        "citations": resolve_citations(answer, sources),
    }


def run_agentic(case: dict) -> dict:
    """Full pipeline: decomposition, then a retrieval pass per sub-query.

    retrieval_k=K matters for the experiment's validity. The default is 4 per
    sub-query (a product decision — several sub-queries would otherwise flood
    the synthesis prompt), but the naive arm retrieves 5 for its single query.
    Comparing those two directly measures k, not decomposition: a first run
    showed the agentic arm "losing" on a medical case purely because its gold
    chunk sat at rank 5 and the agentic arm only took 4. Both arms use the same
    per-query k so the variable under test is actually the variable under test.
    """
    trace = ask(case["question"], domain=case["domain"], log=False, retrieval_k=K)
    return {
        "retrieved_ids": [s.id for s in trace.retrieval.sources],
        "answer": trace.synthesis.answer,
        "citations": trace.synthesis.citations,
        "subqueries": trace.planning.subqueries,
    }


def score_arm(cases: list[dict], runner) -> dict:
    answerable, unanswerable, per_case = [], [], []

    for case in cases:
        got = runner(case)
        record = {
            "id": case["id"],
            "question": case["question"],
            "answerable": case["answerable"],
            "gold_chunk_ids": case["gold_chunk_ids"],
            "retrieved_ids": got["retrieved_ids"],
            "answer": got["answer"],
            "abstained": is_abstention(got["answer"]),
            "citation_accuracy": citation_accuracy(got["citations"]),
            "subqueries": got.get("subqueries", [case["question"]]),
            "notes": case.get("notes", ""),
        }
        if case["answerable"]:
            record["recall@5"] = recall_at_k(got["retrieved_ids"], case["gold_chunk_ids"], K)
            record["mrr"] = reciprocal_rank(got["retrieved_ids"], case["gold_chunk_ids"])
            answerable.append(record)
        else:
            unanswerable.append(record)
        per_case.append(record)

    return {
        "recall@5": mean([r["recall@5"] for r in answerable]),
        "mrr": mean([r["mrr"] for r in answerable]),
        "citation_accuracy": mean([r["citation_accuracy"] for r in per_case]),
        # Abstention is only meaningful where the answer genuinely is not in
        # the corpus. On answerable cases, abstaining is a FAILURE.
        "abstention_rate": mean([1.0 if r["abstained"] else 0.0 for r in unanswerable]),
        "false_abstention_rate": mean([1.0 if r["abstained"] else 0.0 for r in answerable]),
        "n_answerable": len(answerable),
        "n_unanswerable": len(unanswerable),
        "per_case": per_case,
    }


# --------------------------------------------------------------------------
# Experiment 3 — router ablation. Embedding routers cost nothing.
# --------------------------------------------------------------------------

def run_router_ablation(cases: list[dict], ambiguous: list[dict], methods: list[str]) -> dict:
    labelled = [c for c in cases if c["domain"]]
    results = {}

    for method in methods:
        correct = sum(1 for c in labelled if route(c["question"], method=method).domain == c["domain"])
        decisions = [route(c["question"], method=method) for c in ambiguous]
        flagged = sum(1 for d in decisions if not d.is_confident)
        results[method] = {
            "accuracy": round(correct / len(labelled), 4) if labelled else 0.0,
            "correct": correct,
            "n": len(labelled),
            # Does the router KNOW when it cannot separate a question? An LLM
            # router has no calibrated confidence, so this is always 0 for it —
            # which is the point of reporting it.
            "ambiguous_flagged": flagged,
            "n_ambiguous": len(ambiguous),
        }
    return results


# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="PRISM evaluation harness")
    parser.add_argument("--quick", action="store_true",
                        help="Retrieval + routing only — zero LLM calls")
    parser.add_argument("--no-cache", action="store_true",
                        help="Bypass the response cache (costs real quota)")
    parser.add_argument("--llm-router", action="store_true",
                        help="Include the LLM router in the ablation (1 call per question)")
    args = parser.parse_args()

    if not args.no_cache:
        llm_cache.enable()
    llm_cache.reset_stats()
    warm_up()

    financial, medical = load_golden("financial"), load_golden("medical")
    ambiguous = load_golden("ambiguous")
    started = datetime.now(timezone.utc)

    report = {
        "generated_at": started.isoformat(),
        "models": {"generator": LLM_MODEL, "judge": VERIFIER_MODEL, "embeddings": EMBEDDING_MODEL},
        "corpus": {d: len(load_units(d)) for d in ("financial", "medical")},
        "golden_set": {
            "financial": len(financial), "medical": len(medical),
            "ambiguous": len(ambiguous),
            "unanswerable": sum(1 for c in financial + medical if not c["answerable"]),
        },
        "k": K,
    }

    print("Experiment 1 — retrieval ablation (dense vs sparse vs hybrid)")
    report["retrieval_ablation"] = {
        "financial": run_retrieval_ablation(financial),
        "medical": run_retrieval_ablation(medical),
    }
    for domain, arms in report["retrieval_ablation"].items():
        for name, m in arms.items():
            print(f"  {domain:10} {name:7} recall@5={m['recall@5']:.3f}  mrr={m['mrr']:.3f}")

    router_methods = ["embedding:max", "embedding:centroid"] + (["llm"] if args.llm_router else [])
    print("\nExperiment 3 — router ablation")
    report["router_ablation"] = run_router_ablation(financial + medical, ambiguous, router_methods)
    for name, m in report["router_ablation"].items():
        print(f"  {name:20} accuracy={m['accuracy']:.3f} ({m['correct']}/{m['n']})  "
              f"ambiguous flagged={m['ambiguous_flagged']}/{m['n_ambiguous']}")

    if not args.quick:
        print("\nExperiment 2 — pipeline ablation (naive vs agentic)")
        report["pipeline_ablation"] = {}
        for domain, cases in (("financial", financial), ("medical", medical)):
            report["pipeline_ablation"][domain] = {
                "naive": score_arm(cases, run_naive),
                "agentic": score_arm(cases, run_agentic),
            }
            for arm, m in report["pipeline_ablation"][domain].items():
                print(f"  {domain:10} {arm:8} recall@5={m['recall@5']:.3f}  "
                      f"cite={m['citation_accuracy']:.3f}  "
                      f"abstain={m['abstention_rate']:.3f}")

    report["duration_s"] = round((datetime.now(timezone.utc) - started).total_seconds(), 1)
    report["cache"] = llm_cache.stats()

    out = Path("docs/eval_results.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}  ({report['duration_s']}s, "
          f"{report['cache']['misses']} API calls, "
          f"{report['cache']['hits']} served from cache)")
    return report


if __name__ == "__main__":
    main()
