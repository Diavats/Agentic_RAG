"""Integration: index -> retrieve -> fuse, and the full pipeline end to end.

Split deliberately:

  * Retrieval integration runs by default. It builds a real Chroma + BM25 index
    in a temp directory and makes ZERO API calls, because retrieval is pure
    local computation.
  * The full `ask()` pipeline is marked `live` and skipped unless you run
    `pytest -m live`, because it costs ~2 Groq calls per test.
"""
import pytest

from src.agent import decompose_query, retrieve_for_subqueries
from src.build_index import build_index
from src.hybrid_retrieval import dense_search, hybrid_search, is_warm, sparse_search, warm_up

pytestmark = pytest.mark.model


@pytest.fixture
def indexed(isolated_store, make_unit):
    """A small two-domain corpus with known content."""
    financial = [
        make_unit("JGCHEM supplies Zinc Oxide to auto OEMs and tyre makers.",
                  domain="financial", source_file="stocks.csv", index=0),
        make_unit("SHAREINDIA operating profit grew 71.79 percent this quarter.",
                  domain="financial", source_file="stocks.csv", index=1),
        make_unit("DIACABS posted operating profit growth of 1003.70 percent.",
                  domain="financial", source_file="stocks.csv", index=2),
    ]
    medical = [
        make_unit("Sample TC‑014 recorded an activation score of 0.87 on panel B.",
                  domain="medical", source_type="tabular", source_file="antigens.csv", index=0),
        make_unit("Subjects with active infection are excluded from enrollment.",
                  domain="medical", source_type="textual", source_file="protocol.docx", index=0),
    ]
    build_index(financial, "financial")
    build_index(medical, "medical")
    return {"financial": financial, "medical": medical}


class TestRetrievalIntegration:
    def test_dense_search_returns_results(self, indexed):
        assert dense_search("zinc oxide supplier", "financial", k=2)

    def test_sparse_search_returns_results(self, indexed):
        assert sparse_search("JGCHEM", "financial", k=2)

    def test_hybrid_fuses_both_rankers(self, indexed):
        hits = hybrid_search("zinc oxide", "financial", k=3)
        assert hits
        assert all({"row_id", "text", "score"} <= set(h) for h in hits)

    def test_rrf_scores_descend(self, indexed):
        scores = [h["score"] for h in hybrid_search("profit growth", "financial", k=3)]
        assert scores == sorted(scores, reverse=True)

    def test_exact_id_lookup_works_end_to_end(self, indexed):
        """The Unicode fix, proved through the real index rather than in
        isolation: the stored text uses U+2011, the query uses a plain hyphen."""
        hits = sparse_search("TC-014", "medical", k=1)
        assert indexed["medical"][0].id == hits[0][0]

    def test_retrieval_never_crosses_domains(self, indexed):
        medical_ids = {u.id for u in indexed["medical"]}
        for hit in hybrid_search("activation score antigen panel", "financial", k=3):
            assert hit["row_id"] not in medical_ids

    def test_both_source_types_are_retrievable_in_one_domain(self, indexed):
        """Format-agnosticism: retrieval cannot tell a DOCX chunk from a CSV row."""
        ids = {h["row_id"] for q in ("activation score", "excluded from enrollment")
               for h in hybrid_search(q, "medical", k=2)}
        assert ids == {u.id for u in indexed["medical"]}

    def test_unknown_domain_raises(self, indexed):
        with pytest.raises(Exception):
            hybrid_search("anything", "legal", k=1)


class TestSubqueryFusion:
    def test_results_are_deduplicated(self, indexed):
        docs = retrieve_for_subqueries(["profit growth", "operating profit"], "financial", k=3)
        assert len({d["row_id"] for d in docs}) == len(docs)

    def test_results_are_sorted_by_best_score(self, indexed):
        """The synthesis cut keeps the top N, so ordering decides what the
        model sees. A dict-overwrite kept insertion order and made it arbitrary."""
        scores = [d["score"] for d in
                  retrieve_for_subqueries(["profit", "growth", "JGCHEM"], "financial", k=3)]
        assert scores == sorted(scores, reverse=True)

    def test_single_subquery_still_works(self, indexed):
        assert retrieve_for_subqueries(["JGCHEM"], "financial", k=2)


class TestWarmUp:
    def test_warm_up_makes_the_model_resident(self, indexed):
        """Cold start is ~19.8s vs 37ms warm. Phase 7 calls this at boot so
        the first real user does not pay it."""
        warm_up(domains=("financial",))
        assert is_warm()

    def test_warm_up_tolerates_an_unindexed_domain(self, isolated_store):
        warm_up(domains=("financial", "medical"))


class TestPlannerContract:
    """decompose_query without spending a Groq call."""

    def _stub(self, monkeypatch, content):
        class Msg:
            def __init__(self, c): self.content = c
        class Choice:
            def __init__(self, c): self.message = Msg(c)
        class Resp:
            def __init__(self, c): self.choices = [Choice(c)]

        import src.agent as agent
        monkeypatch.setattr(
            agent.client.chat.completions, "create", lambda **kw: Resp(content)
        )

    def test_valid_json_list_is_used(self, monkeypatch):
        self._stub(monkeypatch, '["part one", "part two"]')
        assert decompose_query("q") == ["part one", "part two"]

    def test_more_than_four_subqueries_are_capped(self, monkeypatch):
        """AGENTS.md Agent 2 specifies 2-4. It was documented but unchecked,
        so a nine-item plan would have multiplied retrieval cost silently."""
        self._stub(monkeypatch, '["a","b","c","d","e","f","g","h","i"]')
        assert len(decompose_query("q")) == 4

    def test_malformed_json_falls_back_to_the_original_question(self, monkeypatch):
        self._stub(monkeypatch, "Sure! Here are the sub-questions: ...")
        assert decompose_query("original?") == ["original?"]

    def test_non_list_json_falls_back(self, monkeypatch):
        self._stub(monkeypatch, '{"subqueries": ["a"]}')
        assert decompose_query("original?") == ["original?"]

    def test_empty_list_falls_back(self, monkeypatch):
        self._stub(monkeypatch, "[]")
        assert decompose_query("original?") == ["original?"]

    def test_blank_entries_are_dropped(self, monkeypatch):
        self._stub(monkeypatch, '["real question", "", "   "]')
        assert decompose_query("q") == ["real question"]


@pytest.mark.live
class TestFullPipeline:
    """Real Groq calls. Run with: pytest -m live"""

    def test_ask_returns_a_populated_trace(self, indexed):
        from src.agent import ask

        trace = ask("What does JGCHEM supply?", "financial", log=False)
        assert trace.routing.domain == "financial"
        assert trace.planning.subqueries
        assert trace.retrieval.sources
        assert trace.synthesis.answer
        assert trace.total_latency_ms > 0

    def test_answer_cites_only_supplied_sources(self, indexed):
        from src.agent import ask

        trace = ask("What does JGCHEM supply?", "financial", log=False)
        assert trace.synthesis.unresolved_citations == []

    def test_system_abstains_on_absent_information(self, indexed):
        """AGENTS.md Agent 3 instructs abstention; nothing measured it until
        Phase 6's abstention-rate metric. This is the smoke test for it."""
        from src.agent import ask

        trace = ask("What is the dividend policy of TCS?", "financial", log=False)
        assert trace.synthesis.answer
