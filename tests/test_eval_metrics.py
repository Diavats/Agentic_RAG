"""Evaluation metrics — Phase 6.

Two of these tests exist because the harness produced a FALSE FINDING on its
first run, and the numbers looked plausible enough to publish:

  * The naive arm retrieved k=5 while the agentic arm retrieved k=4 per
    sub-query, so a gold chunk at rank 5 was invisible to the agentic arm. The
    ablation reported "agentic is worse" while measuring k, not decomposition.
  * is_abstention() matched "not mentioned" but missed "do not mention", so a
    correct abstention scored as a confabulation.

A harness that grades the system needs its own tests, or it grades wrong and
nothing catches it.
"""
import json
from pathlib import Path

import pytest

from src.eval.metrics import (
    citation_accuracy,
    hit_at_k,
    is_abstention,
    max_precision_at_k,
    mean,
    normalize_negation,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from src.trace import Citation

GOLD = ["gold_a", "gold_b"]


class TestRecall:
    def test_all_gold_retrieved(self):
        assert recall_at_k(["gold_a", "x", "gold_b"], GOLD, 5) == 1.0

    def test_half_retrieved(self):
        assert recall_at_k(["gold_a", "x", "y"], GOLD, 5) == 0.5

    def test_none_retrieved(self):
        assert recall_at_k(["x", "y"], GOLD, 5) == 0.0

    def test_respects_the_k_cutoff(self):
        """The bug that produced a false finding: a gold chunk at rank 5 is
        found at k=5 and missed at k=4."""
        retrieved = ["a", "b", "c", "d", "gold_a"]
        assert recall_at_k(retrieved, ["gold_a"], 5) == 1.0
        assert recall_at_k(retrieved, ["gold_a"], 4) == 0.0

    def test_no_gold_is_not_a_failure(self):
        """Unanswerable questions have no gold chunks; retrieving nothing
        relevant is correct, not a miss."""
        assert recall_at_k(["x"], [], 5) == 1.0


class TestPrecisionCeiling:
    def test_perfect_retrieval_of_one_gold_chunk_scores_only_one_fifth(self):
        """Why PRD section 7's 'precision@5 >= 80%' target is arithmetically
        unreachable here, and why Recall@5 is the headline metric instead."""
        assert precision_at_k(["gold_a", "x", "y", "z", "w"], ["gold_a"], 5) == 0.2
        assert max_precision_at_k(["gold_a"], 5) == 0.2

    def test_ceiling_rises_with_more_gold_chunks(self):
        assert max_precision_at_k(GOLD, 5) == 0.4

    def test_ceiling_caps_at_one(self):
        assert max_precision_at_k([f"g{i}" for i in range(9)], 5) == 1.0


class TestRanking:
    def test_reciprocal_rank_rewards_rank_one(self):
        assert reciprocal_rank(["gold_a", "x"], GOLD) == 1.0

    def test_reciprocal_rank_decays(self):
        assert reciprocal_rank(["x", "y", "gold_b"], GOLD) == pytest.approx(1 / 3)

    def test_reciprocal_rank_zero_when_absent(self):
        assert reciprocal_rank(["x", "y"], GOLD) == 0.0

    def test_mrr_distinguishes_what_recall_cannot(self):
        """Recall@5 scores rank 1 and rank 5 identically. Ranking is exactly
        what the retrieval ablation is testing, so MRR is reported alongside."""
        first, fifth = ["gold_a", "a", "b", "c", "d"], ["a", "b", "c", "d", "gold_a"]
        assert recall_at_k(first, ["gold_a"], 5) == recall_at_k(fifth, ["gold_a"], 5)
        assert reciprocal_rank(first, ["gold_a"]) > reciprocal_rank(fifth, ["gold_a"])

    def test_hit_at_k_is_binary(self):
        assert hit_at_k(["x", "gold_b"], GOLD, 5) == 1.0
        assert hit_at_k(["x", "y"], GOLD, 5) == 0.0


class TestAbstentionDetection:
    @pytest.mark.parametrize("answer", [
        "The context does not contain information about ibuprofen.",
        "The provided excerpts do not mention the name of the hospital.",
        "The sources don't provide that detail.",
        "I don't have enough context to answer that.",
        "No source in the retrieved context specifies a hospital.",
        "The retrieved context is insufficient to answer this question.",
        "This information is not available in the provided documents.",
        "The documents do not specify an enrollment total.",
    ])
    def test_abstentions_are_detected(self, answer):
        assert is_abstention(answer), f"missed an abstention: {answer!r}"

    @pytest.mark.parametrize("answer", [
        "JGCHEM supplies Zinc Oxide to auto OEMs and tyre makers.",
        "DIACABS grew operating profit by 1003.70 percent.",
        "TC-017 had the highest activation score at 0.91.",
        "Subjects with active infection are excluded from enrollment.",
    ])
    def test_real_answers_are_not_flagged(self, answer):
        assert not is_abstention(answer), f"false abstention: {answer!r}"

    def test_negation_forms_are_normalized(self):
        """The specific miss: a literal phrase list had 'not mentioned' but not
        'do not mention'. Normalizing tense and contraction first is what stops
        that whole class of gap."""
        for phrasing in ["does not mention", "do not mention", "doesn't mention",
                         "did not mention", "cannot mention"]:
            assert "not mention" in normalize_negation(f"The source {phrasing} it.")


class TestCitationAccuracy:
    def test_all_resolved(self):
        cites = [Citation(marker="S1", source_id="a", resolved=True),
                 Citation(marker="S2", source_id="b", resolved=True)]
        assert citation_accuracy(cites) == 1.0

    def test_one_invented_source(self):
        cites = [Citation(marker="S1", source_id="a", resolved=True),
                 Citation(marker="S9", source_id=None, resolved=False)]
        assert citation_accuracy(cites) == 0.5

    def test_uncited_answer_is_not_penalised(self):
        """A correct abstention cites nothing and cannot have a wrong citation."""
        assert citation_accuracy([]) == 1.0


class TestMean:
    def test_rounds_to_four_places(self):
        assert mean([1.0, 0.0, 1.0]) == 0.6667

    def test_empty_is_zero_not_a_crash(self):
        assert mean([]) == 0.0


class TestGoldenSets:
    """The golden sets are data, and wrong data produces confidently wrong
    numbers with nothing to reveal it."""

    @pytest.fixture(scope="class")
    def sets(self):
        d = Path(__file__).resolve().parent.parent / "src" / "eval"
        return {n: json.loads((d / f"golden_{n}.json").read_text(encoding="utf-8"))
                for n in ("financial", "medical", "ambiguous")}

    def test_sizes_meet_the_prd_minimum(self, sets):
        """PRD section 7: at least 15 Q&A per domain."""
        assert len(sets["financial"]) >= 15
        assert len(sets["medical"]) >= 15

    def test_every_case_has_the_required_fields(self, sets):
        required = {"id", "question", "domain", "gold_chunk_ids", "gold_answer",
                    "answerable", "ambiguous", "notes"}
        for cases in sets.values():
            for case in cases:
                assert required <= set(case), f"{case.get('id')} is missing fields"

    def test_ids_are_unique(self, sets):
        ids = [c["id"] for cases in sets.values() for c in cases]
        assert len(ids) == len(set(ids))

    def test_answerable_cases_have_gold_chunks(self, sets):
        for name in ("financial", "medical"):
            for case in sets[name]:
                if case["answerable"]:
                    assert case["gold_chunk_ids"], f"{case['id']} is answerable but unlabelled"

    def test_unanswerable_cases_have_none(self, sets):
        for cases in sets.values():
            for case in cases:
                if not case["answerable"]:
                    assert case["gold_chunk_ids"] == []

    def test_each_domain_includes_unanswerable_cases(self, sets):
        """Without them, abstention cannot be measured and the golden set only
        ever asks questions the corpus can answer — the contamination risk of a
        self-authored set."""
        for name in ("financial", "medical"):
            assert sum(1 for c in sets[name] if not c["answerable"]) >= 3

    @pytest.mark.model
    def test_every_gold_chunk_id_exists_in_the_index(self, sets):
        """A typo here scores retrieval as a permanent miss, and nothing in the
        report would reveal it."""
        from src.unit_store import load_units

        real = {u.id for d in ("financial", "medical") for u in load_units(d)}
        for name in ("financial", "medical"):
            for case in sets[name]:
                for gold in case["gold_chunk_ids"]:
                    assert gold in real, f"{case['id']} references a non-existent chunk: {gold}"
