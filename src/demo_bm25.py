"""
Demonstrate the Unicode bug that had silently disabled keyword search.

    python -m src.demo_bm25

Runs against the REAL medical index, not a fixture, so the numbers printed are
the ones the deployed system would produce.

The bug: BM25 exists in this system to catch exact matches that dense
embeddings miss — ticker symbols, sample IDs, drug names. The narrative
generator is an LLM, and it writes sample IDs using a NON-BREAKING HYPHEN
(U+2011). A human types an ordinary hyphen (U+002D). Those tokenize to
different strings, so the query scored 0.0000 against every document in the
corpus, and BM25 contributed nothing at all to the hybrid fusion.

It failed silently: RRF still returned a ranked list, so the output looked like
ordinary ranking rather than a dead retriever.
"""
import sys

from rank_bm25 import BM25Okapi

from src.build_index import load_bm25, tokenize_for_bm25

QUERY = "TC-014"  # ordinary ASCII hyphen, as a person would type it


def old_tokenizer(text: str) -> list[str]:
    """What the code did before the fix."""
    return text.lower().split()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")

    _, ids, texts = load_bm25("medical")

    print(f"\nCorpus: {len(texts)} medical documents")
    stored = next((w for w in texts[0].split() if "TC" in w), "?")
    print(f"The LLM wrote the sample ID as: {stored!r}")
    print(f"A person searches for:          {QUERY!r}")
    print(f"Same string? {stored.strip('.,') == QUERY}\n")

    print(f"{'tokenizer':42} {'best score':>11}   verdict")
    print("-" * 78)

    results = {}
    for label, tokenizer in (
        ("BEFORE the fix  (plain .lower().split())", old_tokenizer),
        ("AFTER the fix   (Unicode-normalised)", tokenize_for_bm25),
    ):
        bm25 = BM25Okapi([tokenizer(t) for t in texts])
        scores = bm25.get_scores(tokenizer(QUERY))
        best = max(scores)
        results[label] = best
        verdict = "NO MATCH — keyword search is dead" if best == 0 else "match found"
        print(f"{label:42} {best:>11.4f}   {verdict}")

    print("\nWhy a naive test did not catch this:")
    bm25 = BM25Okapi([old_tokenizer(t) for t in texts])
    scores = bm25.get_scores(old_tokenizer(QUERY))
    top_id = ids[max(range(len(ids)), key=lambda i: scores[i])]
    print(f"  With every score at 0.0, sorted() returns insertion order, and the")
    print(f"  target happens to be document 0. So `assert target in results` PASSES:")
    print(f"    top result = {top_id}")
    print(f"    its score  = {scores[ids.index(top_id)]:.4f}")
    print(f"  The test only failed once it asserted on the SCORE instead of on")
    print(f"  whether the document appeared.\n")

    return 0 if list(results.values())[1] > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
