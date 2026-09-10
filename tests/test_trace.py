"""QueryTrace contract and citation resolution.

The regression here is a bug in the measuring instrument itself, which is the
worst kind. The synthesis prompt asks for [S1] and the model usually complies —
but on 3 of the first 10 recorded traces it emitted FULLWIDTH brackets instead:
【S1】. A resolver matching only ASCII brackets reported ZERO citations for those
answers.

Citation accuracy is a PRD section 7 success metric. Left unfixed, the Phase 6
eval harness would have reported it roughly thirty points too low, and the
number would have looked plausible enough to publish.
"""
import json

from src.trace import (
    Citation,
    PlanningStage,
    QueryTrace,
    RetrievalStage,
    RetrievedSource,
    RoutingStage,
    SynthesisStage,
    read_traces,
    resolve_citations,
    timed,
)


def sources(n=3):
    return [
        RetrievedSource(id=f"financial_tabular_stocks_ab12cd_{i:04d}", text=f"doc {i}",
                        score=0.03, rank=i)
        for i in range(1, n + 1)
    ]


class TestCitationBrackets:
    def test_ascii_brackets(self):
        cites = resolve_citations("Revenue rose [S1] and profit fell [S2].", sources())
        assert [c.marker for c in cites] == ["S1", "S2"]
        assert all(c.resolved for c in cites)

    def test_fullwidth_cjk_brackets(self):
        """THE regression — what the model actually emitted."""
        cites = resolve_citations("The score was 0.91【S1】.", sources())
        assert [c.marker for c in cites] == ["S1"]
        assert cites[0].resolved

    def test_fullwidth_square_brackets(self):
        assert [c.marker for c in resolve_citations("Result ［S2］ here.", sources())] == ["S2"]

    def test_mixed_bracket_styles_in_one_answer(self):
        cites = resolve_citations("First [S1], then 【S2】, then ［S3］.", sources())
        assert [c.marker for c in cites] == ["S1", "S2", "S3"]

    def test_internal_whitespace_tolerated(self):
        assert [c.marker for c in resolve_citations("see [ S1 ]", sources())] == ["S1"]

    def test_lowercase_marker_tolerated(self):
        assert [c.marker for c in resolve_citations("see [s1]", sources())] == ["S1"]


class TestCitationResolution:
    def test_marker_maps_to_the_right_source(self):
        cites = resolve_citations("[S2]", sources())
        assert cites[0].source_id == sources()[1].id, "[S1] must be sources[0]"

    def test_repeated_marker_counted_once(self):
        assert len(resolve_citations("[S1] and again [S1] and [S1]", sources())) == 1

    def test_ordered_by_first_appearance(self):
        assert [c.marker for c in resolve_citations("[S3] then [S1]", sources())] == ["S3", "S1"]

    def test_out_of_range_marker_is_flagged_unresolved(self):
        """The model cited a source number it was never given — a free
        hallucination signal, no judge call required."""
        cites = resolve_citations("[S9]", sources(3))
        assert cites[0].resolved is False
        assert cites[0].source_id is None

    def test_zero_marker_is_unresolved(self):
        """[S0] is off-by-one nonsense; sources are 1-indexed."""
        assert resolve_citations("[S0]", sources())[0].resolved is False

    def test_uncited_answer_yields_nothing(self):
        """Correct abstentions have no citations, and that is not an error."""
        assert resolve_citations("The context does not cover this.", sources()) == []

    def test_prose_brackets_are_not_mistaken_for_citations(self):
        assert resolve_citations("See [note] and [Section 4].", sources()) == []


class TestTraceModel:
    def build(self, answer="Result [S1].", cold=False):
        srcs = sources()
        return QueryTrace(
            question="q?",
            routing=RoutingStage(domain="financial", method="explicit"),
            planning=PlanningStage(subqueries=["a", "b"], was_decomposed=True, latency_ms=100),
            retrieval=RetrievalStage(sources=srcs, n_candidates=5, latency_ms=50),
            synthesis=SynthesisStage(
                answer=answer, citations=resolve_citations(answer, srcs), latency_ms=200
            ),
            total_latency_ms=350,
            cold_start=cold,
        )

    def test_unresolved_citations_surfaced(self):
        assert self.build("Claim [S9].").synthesis.unresolved_citations == ["S9"]

    def test_summary_flags_unresolved(self):
        assert "UNRESOLVED" in self.build("Claim [S9].").summary()

    def test_summary_flags_cold_start(self):
        """Cold and warm latencies must never be averaged — ~19.8s vs 37ms."""
        assert "COLD" in self.build(cold=True).summary()
        assert "COLD" not in self.build(cold=False).summary()

    def test_verification_is_optional_until_phase_5_5(self):
        assert self.build().verification is None

    def test_round_trips_through_json(self):
        """It is the API response body and the eval record, so serialization
        is a contract, not a convenience."""
        original = self.build()
        restored = QueryTrace.model_validate_json(original.model_dump_json())
        assert restored.question == original.question
        assert restored.retrieval.sources[0].id == original.retrieval.sources[0].id
        assert restored.synthesis.citations == original.synthesis.citations

    def test_trace_ids_are_unique(self):
        assert self.build().trace_id != self.build().trace_id

    def test_append_writes_one_json_object_per_line(self, tmp_path):
        path = tmp_path / "traces.jsonl"
        self.build().append_to_log(path)
        self.build().append_to_log(path)
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert all(json.loads(line)["question"] == "q?" for line in lines)

    def test_read_traces_round_trips(self, tmp_path):
        path = tmp_path / "traces.jsonl"
        self.build().append_to_log(path)
        assert len(read_traces(path)) == 1

    def test_read_traces_on_missing_file_returns_empty(self, tmp_path):
        assert read_traces(tmp_path / "nope.jsonl") == []


class TestTimed:
    def test_records_elapsed_milliseconds(self):
        import time

        got = {}
        with timed(got, "stage"):
            time.sleep(0.02)
        assert got["stage"] >= 15

    def test_records_even_when_the_block_raises(self):
        """A latency of zero on a failed stage would be a lie."""
        got = {}
        try:
            with timed(got, "stage"):
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        assert "stage" in got
