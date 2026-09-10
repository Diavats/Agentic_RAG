"""Groundedness self-check — Phase 5.5.

The property that matters is DISCRIMINATION. A verifier that returns 1.0 for
everything is worse than no verifier, because it launders unchecked output as
checked. The stubbed tests pin the mechanics; the `live` tests prove the real
judge separates grounded answers from fabricated ones.

Measured against the real qwen judge (a different family from the gpt-oss
generator, deliberately):

    fully grounded          1.00  (2/2)
    one fabricated number   0.50  (1/2)
    entirely fabricated     0.00  (0/4)
    correct abstention      1.00  (0/0)
"""
import pytest

from src.trace import RetrievedSource
from src.verifier import _sources_for_claim, extract_claims, verify_answer


def sources(n=3):
    return [
        RetrievedSource(id=f"doc_{i}", rank=i, score=0.03, text=f"Source text {i}.")
        for i in range(1, n + 1)
    ]


@pytest.fixture
def judge(monkeypatch):
    """Stub the judge. Returns a recorder you can program and inspect."""
    calls = []

    class Recorder:
        verdicts: list[str] = []
        claims_json = '["claim one [S1]", "claim two [S2]"]'

        def __call__(self, prompt, model):
            calls.append((prompt, model))
            if "atomic factual claims" in prompt:
                return self.claims_json
            return self.verdicts.pop(0) if self.verdicts else "SUPPORTED"

    recorder = Recorder()
    recorder.calls = calls
    import src.verifier as verifier

    monkeypatch.setattr(verifier, "_ask_judge", recorder)
    return recorder


class TestScoring:
    def test_all_claims_supported_scores_one(self, judge):
        judge.verdicts = ["SUPPORTED", "SUPPORTED"]
        result = verify_answer("answer", sources())
        assert (result.supported_claims, result.total_claims, result.score) == (2, 2, 1.0)

    def test_half_supported_scores_half(self, judge):
        judge.verdicts = ["SUPPORTED", "UNSUPPORTED"]
        assert verify_answer("answer", sources()).score == 0.5

    def test_none_supported_scores_zero(self, judge):
        judge.verdicts = ["UNSUPPORTED", "UNSUPPORTED"]
        assert verify_answer("answer", sources()).score == 0.0

    def test_unsupported_is_not_read_as_supported(self, judge):
        """'UNSUPPORTED' contains 'SUPPORTED' as a substring — a naive
        `if "SUPPORTED" in verdict` scores every rejection as a pass, turning
        the checker into a rubber stamp that always returns 1.0."""
        judge.verdicts = ["UNSUPPORTED", "UNSUPPORTED"]
        assert verify_answer("answer", sources()).supported_claims == 0

    def test_verdict_case_and_padding_tolerated(self, judge):
        judge.verdicts = ["  supported  ", "Unsupported."]
        assert verify_answer("answer", sources()).supported_claims == 1


class TestAbstention:
    def test_an_answer_with_no_claims_scores_one(self, judge):
        """A correct abstention is perfectly grounded. Scoring it 0.0 would
        punish exactly the behaviour the system is supposed to have."""
        judge.claims_json = "[]"
        result = verify_answer("The context does not cover this.", sources())
        assert (result.total_claims, result.score) == (0, 1.0)

    def test_empty_answer_makes_no_judge_calls(self, judge):
        assert verify_answer("", sources()).total_claims == 0
        assert judge.calls == []


class TestClaimExtraction:
    def test_json_list_is_parsed(self, judge):
        judge.claims_json = '["one", "two"]'
        assert extract_claims("answer") == ["one", "two"]

    def test_json_wrapped_in_prose_is_recovered(self, judge):
        judge.claims_json = 'Here you go:\n```json\n["one"]\n```'
        assert extract_claims("answer") == ["one"]

    def test_unparseable_output_yields_no_claims(self, judge):
        """Never raise mid-answer — a broken judge must not take down a good
        answer that has already been generated."""
        judge.claims_json = "I could not parse that."
        assert extract_claims("answer") == []

    def test_a_list_wrapped_in_an_object_is_recovered(self, judge):
        """The model was asked for a bare list and returned {"claims": [...]}.
        Recovering the inner list is the same lenient behaviour as pulling JSON
        out of surrounding prose — discarding usable output because the wrapper
        was wrong would be strictness for its own sake."""
        judge.claims_json = '{"claims": ["one"]}'
        assert extract_claims("answer") == ["one"]

    def test_output_with_no_json_at_all_yields_no_claims(self, judge):
        judge.claims_json = "The answer makes several points about the data."
        assert extract_claims("answer") == []

    def test_blank_entries_dropped(self, judge):
        judge.claims_json = '["real", "", "   "]'
        assert extract_claims("answer") == ["real"]

    def test_claim_count_is_capped(self, judge):
        """Verification costs one call per claim. A rambling answer must not be
        able to spend thirty calls of a limited daily quota."""
        judge.claims_json = "[" + ", ".join(f'"c{i}"' for i in range(40)) + "]"
        assert len(extract_claims("answer")) == 12


class TestClaimToSourceMapping:
    def test_a_cited_claim_checks_only_its_own_source(self):
        assert [s.id for s in _sources_for_claim("Revenue rose [S2].", sources())] == ["doc_2"]

    def test_multiple_citations_are_all_included(self):
        got = _sources_for_claim("Both [S1] and [S3] agree.", sources())
        assert {s.id for s in got} == {"doc_1", "doc_3"}

    def test_fullwidth_brackets_are_understood(self):
        """Same bug class as the trace's citation parser — the model emits 【S1】."""
        assert [s.id for s in _sources_for_claim("Score was 0.91【S2】.", sources())] == ["doc_2"]

    def test_an_uncited_claim_checks_against_everything(self):
        """Otherwise the score measures citation discipline rather than
        groundedness. Missing markers are already reported separately, as
        unresolved citations on the trace."""
        assert len(_sources_for_claim("Revenue rose.", sources())) == 3

    def test_an_out_of_range_citation_falls_back_to_everything(self):
        assert len(_sources_for_claim("Claim [S9].", sources(3))) == 3


class TestReporting:
    def test_judge_model_is_recorded(self, judge):
        """The eval must be able to state who graded it. A result without a
        named judge is not reproducible."""
        from src.config import VERIFIER_MODEL

        assert verify_answer("answer", sources()).judge_model == VERIFIER_MODEL

    def test_judge_differs_from_the_generator(self):
        """A model grading its own output is a biased judge. gpt-oss-120b would
        be a bigger sibling of the generator, not an independent one."""
        from src.config import LLM_MODEL, VERIFIER_MODEL

        assert VERIFIER_MODEL != LLM_MODEL
        assert VERIFIER_MODEL.split("/")[0] != LLM_MODEL.split("/")[0]

    def test_latency_is_recorded(self, judge):
        assert verify_answer("answer", sources()).latency_ms >= 0


class TestPipelineIntegration:
    def test_verification_is_off_by_default(self, monkeypatch):
        """It roughly doubles latency and API spend, so it is opt-in."""
        import src.agent as agent
        import src.verifier as verifier

        monkeypatch.setattr(agent, "decompose_query", lambda q: [q])
        monkeypatch.setattr(agent, "synthesize_answer", lambda q, s: "Answer [S1].")
        monkeypatch.setattr(
            agent, "retrieve_for_subqueries",
            lambda sq, d, k=4: [{"row_id": "x", "text": "t", "score": 0.1}],
        )
        monkeypatch.setattr(
            verifier, "_ask_judge",
            lambda p, m: pytest.fail("verifier ran without verify=True"),
        )
        assert agent.ask("q", domain="financial", log=False).verification is None

    def test_verification_populates_the_trace_when_asked(self, monkeypatch, judge):
        import src.agent as agent

        monkeypatch.setattr(agent, "decompose_query", lambda q: [q])
        monkeypatch.setattr(agent, "synthesize_answer", lambda q, s: "Answer [S1].")
        monkeypatch.setattr(
            agent, "retrieve_for_subqueries",
            lambda sq, d, k=4: [{"row_id": "x", "text": "t", "score": 0.1}],
        )
        judge.verdicts = ["SUPPORTED", "SUPPORTED"]

        trace = agent.ask("q", domain="financial", log=False, verify=True)
        assert trace.verification is not None
        assert "verify=2/2" in trace.summary()


@pytest.mark.live
class TestRealJudgeDiscriminates:
    """The tests that actually matter: does the real judge tell grounded from
    fabricated? Everything above only proves the plumbing works."""

    SOURCES = [
        RetrievedSource(
            id="s1", rank=1, score=0.03,
            text="Sample TC-014 was tested with antigen panel B at the 48-hour "
                 "timepoint and produced an activation score of 0.87.",
        ),
        RetrievedSource(
            id="s2", rank=2, score=0.03,
            text="Sample TC-015 was tested with antigen panel B and produced an "
                 "activation score of 0.12, indicating no significant activation.",
        ),
    ]

    def test_a_grounded_answer_scores_high(self):
        result = verify_answer(
            "Sample TC-014 scored 0.87 [S1]. Sample TC-015 scored 0.12 [S2].", self.SOURCES
        )
        assert result.score >= 0.8

    def test_a_fabricated_answer_scores_low(self):
        result = verify_answer(
            "Sample TC-099 was tested with panel Z and scored 0.55 [S1]. "
            "The study enrolled 400 subjects across 12 sites [S2].", self.SOURCES
        )
        assert result.score <= 0.25

    def test_it_catches_a_single_wrong_number(self):
        """The realistic failure: mostly right, one invented figure."""
        result = verify_answer(
            "Sample TC-014 scored 0.87 [S1]. Sample TC-015 scored 0.99 [S2].", self.SOURCES
        )
        assert result.score < 1.0
