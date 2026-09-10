"""Domain router — Phase 5.

The embedding router needs no API calls, so nearly everything here runs by
default. The LLM router is stubbed except for one `live` smoke test.

The property under test is not "the router is clever". It is that CONFIDENCE
MEANS SOMETHING. TRD section 5 and AGENTS.md both specify a fallback below 0.7
confidence, using a number the LLM reports about itself — which is uncalibrated
and sits near 0.95 for everything, including mistakes, so that fallback would
never fire. These tests pin the replacement: a cosine margin that is genuinely
small for questions the corpora cannot separate.
"""
import pytest

from src.build_index import build_index
from src.domain_router import (
    LOW_CONFIDENCE_MARGIN,
    RoutingDecision,
    route,
    route_embedding,
    route_llm,
)

pytestmark = pytest.mark.model


@pytest.fixture
def routed(isolated_store, make_unit):
    """Two corpora with clearly different vocabulary."""
    build_index(
        [
            make_unit("JGCHEM supplies Zinc Oxide to auto OEMs and tyre manufacturers.",
                      domain="financial", source_file="stocks.csv", index=0),
            make_unit("SHAREINDIA quarterly revenue and operating profit grew strongly.",
                      domain="financial", source_file="stocks.csv", index=1),
        ],
        "financial",
    )
    build_index(
        [
            make_unit("Subjects with active infection are excluded from enrollment.",
                      domain="medical", source_type="textual",
                      source_file="protocol.docx", index=0),
            make_unit("Sample TC-014 recorded an activation score of 0.87 on antigen panel B.",
                      domain="medical", source_type="tabular",
                      source_file="antigens.csv", index=0),
        ],
        "medical",
    )


class TestRoutingCorrectness:
    @pytest.mark.parametrize(
        "question, expected",
        [
            ("Which company supplies zinc oxide to tyre makers?", "financial"),
            ("What was the quarterly operating profit?", "financial"),
            ("Who is excluded from enrollment in the study?", "medical"),
            ("What antigen panel was used for the assay?", "medical"),
        ],
    )
    def test_routes_unambiguous_questions_correctly(self, routed, question, expected):
        assert route_embedding(question).domain == expected

    def test_decision_reports_a_score_per_domain(self, routed):
        assert set(route_embedding("zinc oxide").scores) == {"medical", "financial"}

    def test_centroid_scoring_also_works(self, routed):
        assert route_embedding("zinc oxide supplier", scoring="centroid").domain == "financial"

    def test_method_is_recorded_for_the_trace(self, routed):
        """Phase 6 compares routers, so each decision must say which it was."""
        assert route_embedding("zinc oxide").method == "embedding:max"
        assert route_embedding("zinc oxide", scoring="centroid").method == "embedding:centroid"

    def test_routing_is_deterministic(self, routed):
        first = route_embedding("quarterly profit")
        assert route_embedding("quarterly profit").model_dump() == first.model_dump()


class TestConfidenceIsCalibrated:
    """The point of replacing the LLM's self-reported number."""

    def test_an_on_topic_question_clears_the_threshold(self, routed):
        assert route_embedding("Which company supplies zinc oxide?").is_confident

    def test_a_contentless_question_does_not(self, routed):
        """'Which one performed best?' fits both corpora equally — the system
        should search both rather than pick one and sound certain."""
        assert not route_embedding("Which one performed best?").is_confident

    def test_margin_separates_on_topic_from_contentless(self, routed):
        on_topic = route_embedding("Who is excluded from enrollment?").margin
        contentless = route_embedding("Show me the highest value.").margin
        assert on_topic > contentless

    def test_margin_is_the_gap_between_the_two_scores(self, routed):
        decision = route_embedding("zinc oxide")
        ranked = sorted(decision.scores.values(), reverse=True)
        assert decision.margin == pytest.approx(ranked[0] - ranked[1], abs=1e-3)

    def test_confidence_stays_in_range(self, routed):
        for q in ["zinc oxide", "antigen panel", "which one?", ""]:
            assert 0.0 <= route_embedding(q).confidence <= 1.0

    def test_threshold_sits_between_the_measured_groups(self):
        """Documented calibration: contentless questions measured 0.016-0.048,
        real questions 0.252 and up. Guard against someone 'tidying' this to a
        round number that swallows real questions."""
        assert 0.05 < LOW_CONFIDENCE_MARGIN < 0.25


class TestNoIndex:
    def test_routing_without_an_index_raises_actionably(self, isolated_store):
        with pytest.raises(RuntimeError, match="setup"):
            route_embedding("anything")


class TestLLMRouter:
    def _stub(self, monkeypatch, content):
        class Msg:
            def __init__(self, c): self.content = c
        class Choice:
            def __init__(self, c): self.message = Msg(c)
        class Resp:
            def __init__(self, c): self.choices = [Choice(c)]

        import src.domain_router as dr

        class FakeClient:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kw): return Resp(content)

        monkeypatch.setattr(dr, "_client", lambda: FakeClient)

    def test_clean_json_is_parsed(self, monkeypatch):
        self._stub(monkeypatch, '{"domain": "medical"}')
        assert route_llm("q").domain == "medical"

    def test_json_wrapped_in_prose_is_recovered(self, monkeypatch):
        """Models pad JSON with explanation despite being told not to."""
        self._stub(monkeypatch, 'Sure!\n```json\n{"domain": "financial"}\n```\nHope that helps.')
        assert route_llm("q").domain == "financial"

    def test_an_invalid_domain_is_rejected(self, monkeypatch):
        """Pydantic, not the prompt, is what enforces the two-value enum."""
        self._stub(monkeypatch, '{"domain": "legal"}')
        with pytest.raises(ValueError):
            route_llm("q", retries=0)

    def test_unparseable_output_raises_after_retries(self, monkeypatch):
        self._stub(monkeypatch, "I think this is about medicine.")
        with pytest.raises(ValueError, match="unusable"):
            route_llm("q", retries=1)

    def test_llm_router_reports_no_margin(self, monkeypatch):
        """It has no calibrated confidence to offer, and inventing one would be
        worse than admitting it."""
        self._stub(monkeypatch, '{"domain": "medical"}')
        assert route_llm("q").margin is None

    def test_llm_decision_is_always_confident(self, monkeypatch):
        """margin=None means the low-confidence path cannot trigger, so an LLM
        route always commits to one corpus."""
        self._stub(monkeypatch, '{"domain": "medical"}')
        assert route_llm("q").is_confident


class TestRouteDispatch:
    def test_default_is_the_embedding_router(self, routed):
        assert route("zinc oxide").method.startswith("embedding")

    def test_centroid_variant_selectable(self, routed):
        assert route("zinc oxide", method="embedding:centroid").method == "embedding:centroid"

    def test_unknown_method_raises(self, routed):
        with pytest.raises(ValueError, match="Unknown routing method"):
            route("q", method="magic")


class TestPipelineIntegration:
    def test_ask_without_a_domain_routes_itself(self, routed, monkeypatch):
        """The headline behaviour: the user never picks a domain."""
        import src.agent as agent

        monkeypatch.setattr(agent, "decompose_query", lambda q: [q])
        monkeypatch.setattr(agent, "synthesize_answer", lambda q, s: "Answer [S1].")

        trace = agent.ask("Who is excluded from enrollment?", log=False)
        assert trace.routing.domain == "medical"
        assert trace.routing.method == "embedding:max"
        assert trace.routing.margin is not None

    def test_explicit_domain_overrides_the_router(self, routed, monkeypatch):
        """The eval harness needs this to measure retrieval independently."""
        import src.agent as agent

        monkeypatch.setattr(agent, "decompose_query", lambda q: [q])
        monkeypatch.setattr(agent, "synthesize_answer", lambda q, s: "Answer [S1].")

        trace = agent.ask("Who is excluded?", domain="financial", log=False)
        assert trace.routing.domain == "financial"
        assert trace.routing.method == "explicit"

    def test_low_confidence_searches_both_corpora(self, routed, monkeypatch):
        """The design decision worth defending: when unsure, return slightly
        noisy results rather than a confident answer from the wrong corpus."""
        import src.agent as agent

        monkeypatch.setattr(agent, "decompose_query", lambda q: [q])
        monkeypatch.setattr(agent, "synthesize_answer", lambda q, s: "Answer [S1].")

        trace = agent.ask("Which one performed best?", log=False)
        assert trace.routing.domain == "both"
        assert "searched both" in trace.routing.method
        assert {s.domain for s in trace.retrieval.sources} == {"medical", "financial"}

    def test_sources_record_which_corpus_they_came_from(self, routed, monkeypatch):
        import src.agent as agent

        monkeypatch.setattr(agent, "decompose_query", lambda q: [q])
        monkeypatch.setattr(agent, "synthesize_answer", lambda q, s: "Answer [S1].")

        trace = agent.ask("Who is excluded from enrollment?", log=False)
        assert all(s.domain == "medical" for s in trace.retrieval.sources)

    def test_routing_latency_is_recorded(self, routed, monkeypatch):
        """TRD section 7 budgets < 1500ms for routing. Measured warm: ~35ms."""
        import src.agent as agent

        monkeypatch.setattr(agent, "decompose_query", lambda q: [q])
        monkeypatch.setattr(agent, "synthesize_answer", lambda q, s: "Answer [S1].")

        assert agent.ask("Who is excluded?", log=False).routing.latency_ms > 0


@pytest.mark.live
class TestLLMRouterLive:
    def test_real_llm_router_classifies_correctly(self, routed):
        assert route_llm("What was the activation score for sample TC-014?").domain == "medical"
