"""
Evaluation metrics.

--- Why the headline retrieval metric is Recall@k, not Precision@k ---

PRD section 7 targets "retrieval precision@5 >= 80%". That target is not merely
hard at this corpus size — it is ARITHMETICALLY IMPOSSIBLE for most of the
golden set, and publishing a number against it would have been misleading.

Precision@5 = (relevant documents in the top 5) / 5. Most questions here have
exactly ONE relevant chunk, because one stock is one row is one chunk. Perfect
retrieval — the gold chunk ranked first — therefore scores 1/5 = 0.20. The
system would have "failed" an 80% target while doing everything right.

Worse, precision@k with few relevant documents mostly measures how many gold
chunks each question happens to have. It grades the golden set, not the
retriever.

Recall@k asks the question that actually matters for RAG: did the evidence
reach the synthesizer? It is not capped by corpus size, and it is directly
interpretable — 0.90 means nine times in ten the model had what it needed.

MRR is reported alongside because Recall@5 cannot tell rank 1 from rank 5, and
ranking is precisely what the retrieval ablation is testing. Precision@k is
still computed and reported, clearly labelled with its ceiling, so the number
PRD section 7 asked for is present rather than quietly dropped.
"""


def recall_at_k(retrieved_ids: list[str], gold_ids: list[str], k: int = 5) -> float:
    """Fraction of gold chunks that reached the top k. The headline metric."""
    if not gold_ids:
        return 1.0  # nothing to find; not a retrieval failure
    top = set(retrieved_ids[:k])
    return len([g for g in gold_ids if g in top]) / len(gold_ids)


def precision_at_k(retrieved_ids: list[str], gold_ids: list[str], k: int = 5) -> float:
    """Reported for completeness. See the module docstring for its ceiling:
    with one gold chunk, a perfect retriever scores 1/k."""
    if not gold_ids or k == 0:
        return 0.0
    return len([r for r in retrieved_ids[:k] if r in set(gold_ids)]) / k


def max_precision_at_k(gold_ids: list[str], k: int = 5) -> float:
    """The best precision@k this question could possibly achieve.

    Reported next to precision so a reader can see immediately that 0.20 is a
    perfect score for a single-gold-chunk question, not a failure.
    """
    if not gold_ids or k == 0:
        return 0.0
    return min(len(gold_ids), k) / k


def hit_at_k(retrieved_ids: list[str], gold_ids: list[str], k: int = 5) -> float:
    """Did ANY gold chunk make the top k? The simplest thing to explain."""
    if not gold_ids:
        return 1.0
    return 1.0 if set(retrieved_ids[:k]) & set(gold_ids) else 0.0


def reciprocal_rank(retrieved_ids: list[str], gold_ids: list[str]) -> float:
    """1 / rank of the first gold chunk, or 0 if none was retrieved.

    Sensitive to ranking, which Recall@5 is not — a gold chunk at rank 1 and at
    rank 5 score identically on recall but 1.0 vs 0.2 here. That is the
    difference the retrieval ablation exists to measure.
    """
    if not gold_ids:
        return 1.0
    gold = set(gold_ids)
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in gold:
            return 1.0 / rank
    return 0.0


def citation_accuracy(citations: list) -> float:
    """Fraction of [Sn] markers that point at a source that was actually
    supplied. An unresolved marker means the model invented a source number —
    a hallucination signal costing no judge call at all."""
    if not citations:
        return 1.0  # an uncited answer cannot have a wrong citation
    return len([c for c in citations if c.resolved]) / len(citations)


# Collapse the many ways English negates, so the stem list below does not have
# to enumerate every tense and contraction. A first version listed literal
# phrases and matched "not mentioned" but MISSED "do not mention" — scoring a
# perfectly good abstention as a confabulation, and making the agentic arm look
# worse than it was. Normalizing first is what stops that class of miss.
_NEGATION_FORMS = (
    ("does not ", "not "), ("do not ", "not "), ("did not ", "not "),
    ("doesn't ", "not "), ("don't ", "not "), ("didn't ", "not "),
    ("is not ", "not "), ("are not ", "not "), ("was not ", "not "),
    ("were not ", "not "), ("isn't ", "not "), ("aren't ", "not "),
    ("cannot ", "not "), ("can't ", "not "), ("could not ", "not "),
    ("couldn't ", "not "), ("there is no ", "no "), ("there are no ", "no "),
)

ABSTENTION_STEMS = (
    "not mention", "not contain", "not cover", "not provide", "not include",
    "not specif", "not state", "not name", "not report", "not appear",
    "not available", "not present", "not answer", "not found", "not given",
    "not in the", "no information", "no data", "no mention", "no source",
    "no details", "no reference", "insufficient", "unable to", "lack",
    # "I don't have enough context" normalizes to "not have enough context",
    # where no stem above appears contiguously — the negation lands on "have",
    # not on the verb that carries the meaning.
    "enough context", "enough information", "not have enough", "limited information",
)


def normalize_negation(text: str) -> str:
    lowered = text.lower()
    for form, replacement in _NEGATION_FORMS:
        lowered = lowered.replace(form, replacement)
    return lowered


def is_abstention(answer: str) -> bool:
    """Did the system decline to answer rather than confabulate?

    AGENTS.md Agent 3 instructs the synthesizer to say what is missing; nothing
    in the project measured whether it does, until this.

    Stem matching after negation-normalization is crude — the honest
    alternative is a judge call per case, which costs quota to measure
    something the synthesis prompt already asks for in fairly stereotyped
    wording. The eval reports abstention only on cases whose ground truth is
    'unanswerable', and reports FALSE abstention separately on answerable ones,
    so over-matching shows up as a visible cost rather than a free win.
    """
    normalized = normalize_negation(answer)
    return any(stem in normalized for stem in ABSTENTION_STEMS)


def mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0
