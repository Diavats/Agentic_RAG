"""
Blind evaluation: questions from people who never saw the corpus.

    python -m src.eval.run_blind

Runs the DEPLOYED configuration — no domain given (the router decides),
verify on (the UI sends verify: true) — because the point is to measure what a
visitor gets, not a tuned eval arm.

Order of operations, which git history shows:
  1. blind_questions.txt committed (questions verbatim)
  2. blind_expected.json committed (answer key written from the corpus)
  3. this run  ->  docs/blind_results.json
  4. blind_grades.json: the builder grades each answer against the key

Step 4 is a human judgment by the person who built the system. The report
says so; the LLM judge is not used for it because judge-human agreement was
never validated.
"""
import json
import re
from pathlib import Path

from src import llm_cache
from src.agent import ask
from src.eval.metrics import citation_accuracy, is_abstention, recall_at_k
from src.hybrid_retrieval import warm_up

EVAL_DIR = Path(__file__).parent
OUT = Path("docs/blind_results.json")


def load_blind_questions(path: Path = EVAL_DIR / "blind_questions.txt") -> list[dict]:
    """Parse '# --- who ---' headers and 'N. question [asker's note]' lines.

    The bracketed note is the asker's expectation, not part of the question —
    sending it would hand the system the answer ("should say it cannot
    determine this").
    """
    cases, who = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        header = re.match(r"#\s*---\s*(.+?)\s*---", line)
        if header:
            who = re.sub(r"\s+", "", header.group(1))
            continue
        item = re.match(r"(\d+)\.\s+(.*)", line)
        if item and who:
            question = re.sub(r"\s*\[[^\]]*\]\s*$", "", item.group(2)).strip()
            cases.append({"id": f"{who}_{item.group(1)}", "question": question})
    return cases


def main():
    llm_cache.enable()
    llm_cache.reset_stats()
    warm_up()

    key = {c["id"]: c for c in json.loads(
        (EVAL_DIR / "blind_expected.json").read_text(encoding="utf-8"))["cases"]}
    records = []
    for case in load_blind_questions():
        expected = key[case["id"]]  # KeyError = a question with no answer key
        trace = ask(case["question"], log=False, verify=True)
        retrieved = [s.id for s in trace.retrieval.sources]
        records.append({
            "id": case["id"],
            "question": case["question"],
            "kind": expected["kind"],
            "answerable": expected["answerable"],
            "expected_domain": expected["domain"],
            "routed_to": trace.routing.domain,
            "router_margin": trace.routing.margin,
            "gold_chunk_ids": expected["gold_chunk_ids"],
            "retrieved_ids": retrieved,
            "recall": recall_at_k(retrieved, expected["gold_chunk_ids"], len(retrieved)),
            "answer": trace.synthesis.answer,
            "abstained": is_abstention(trace.synthesis.answer),
            "citation_accuracy": citation_accuracy(trace.synthesis.citations),
            "groundedness": trace.verification.score if trace.verification else None,
            "subqueries": trace.planning.subqueries,
        })
        r = records[-1]
        print(f"{r['id']:14} routed={r['routed_to']:9} recall={r['recall']:.2f} "
              f"abstained={r['abstained']!s:5} grounded={r['groundedness']}")

    OUT.write_text(json.dumps({"cases": records, "cache": llm_cache.stats()},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}  {llm_cache.stats()}")


if __name__ == "__main__":
    main()
