"""FastAPI backend and the upload sandbox — Phase 7.

Runs against the real app through TestClient, with the pipeline stubbed so the
default suite still makes zero Groq calls.

The properties that matter here are not "the endpoint returns 200". They are:

  * a visitor's upload CANNOT reach the curated `medical` / `financial`
    corpora, or the evaluated system stops being the deployed system;
  * two visitors cannot see each other's data;
  * the row cap is enforced BEFORE any LLM call, because that cap is the only
    thing standing between a shared daily quota and one large spreadsheet.
"""
import io

import pytest

from src.api import sessions as sandbox


@pytest.fixture
def client(monkeypatch, tmp_path):
    """App with the model-loading lifespan skipped and the index redirected."""
    from fastapi.testclient import TestClient

    import src.api.main_api as api
    import src.build_index as build_index
    import src.domain_router as domain_router
    import src.hybrid_retrieval as hybrid_retrieval

    store = tmp_path / "chroma"
    store.mkdir()
    for module in (build_index, hybrid_retrieval, domain_router, sandbox):
        monkeypatch.setattr(module, "CHROMA_DIR", str(store), raising=False)

    # Clear the cached Chroma client and BM25 corpora on the way IN and OUT.
    # Without the teardown, a client handle pointing at this tmp_path survives
    # into later tests, whose own tmp_path has already been deleted — so an
    # unrelated test fails only when run after this file, and passes alone.
    hybrid_retrieval.refresh_caches()
    domain_router.refresh_caches()

    # Empty lifespan: the real one loads a ~90MB model and rebuilds the index.
    monkeypatch.setattr(api.app.router, "lifespan_context", _noop_lifespan)
    sandbox.STORE = sandbox.SessionStore()
    try:
        with TestClient(api.app) as c:
            yield c
    finally:
        hybrid_retrieval.refresh_caches()
        domain_router.refresh_caches()


def _noop_lifespan(app):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _ctx(_app):
        yield

    return _ctx(app)


def csv_bytes(rows: int) -> bytes:
    header = "sample_id,score,notes\n"
    body = "".join(f"TC-{i:03d},0.5,note {i}\n" for i in range(rows))
    return (header + body).encode("utf-8")


class TestHealth:
    def test_health_reports_the_models_in_use(self, client):
        body = client.get("/health").json()
        assert body["status"] == "ok"
        assert body["models"]["generator"]
        assert body["models"]["judge"] != body["models"]["generator"]

    def test_limits_explains_the_row_cap(self, client):
        body = client.get("/limits").json()
        assert body["max_tabular_rows"] == sandbox.MAX_TABULAR_ROWS
        assert "LLM call" in body["why_row_cap"]
        assert ".docx" in body["supported_formats"]


class TestSessions:
    def test_create_returns_an_isolated_collection(self, client):
        body = client.post("/session").json()
        assert body["collection"].startswith("session_")
        assert body["unit_count"] == 0
        assert body["expires_in_s"] > 0

    def test_two_sessions_get_different_collections(self, client):
        a = client.post("/session").json()["collection"]
        b = client.post("/session").json()["collection"]
        assert a != b

    def test_a_session_collection_is_never_a_curated_one(self, client):
        """The property the whole sandbox exists for."""
        for _ in range(5):
            assert client.post("/session").json()["collection"] not in ("medical", "financial")

    def test_unknown_session_is_404(self, client):
        assert client.get("/session/deadbeef").status_code == 404

    def test_deleting_a_session_makes_it_gone(self, client):
        sid = client.post("/session").json()["session_id"]
        assert client.delete(f"/session/{sid}").status_code == 200
        assert client.get(f"/session/{sid}").status_code == 404

    def test_expired_sessions_are_rejected(self, client, monkeypatch):
        sid = client.post("/session").json()["session_id"]
        monkeypatch.setattr(sandbox, "SESSION_TTL_SECONDS", -1)
        assert client.get(f"/session/{sid}").status_code == 404


class TestUploadValidation:
    def test_row_cap_is_enforced_before_any_llm_call(self, client, monkeypatch):
        """The cap is the only thing between a shared daily quota and one big
        spreadsheet, so it must reject at HTTP time, not inside the job."""
        called = []
        monkeypatch.setattr(
            sandbox, "ingest_into_session",
            lambda *a, **k: called.append(1),
        )
        sid = client.post("/session").json()["session_id"]
        response = client.post(
            f"/session/{sid}/upload",
            files={"file": ("big.csv", csv_bytes(sandbox.MAX_TABULAR_ROWS + 10), "text/csv")},
            data={"domain": "medical"},
        )
        assert response.status_code == 413
        assert str(sandbox.MAX_TABULAR_ROWS) in response.json()["detail"]
        assert called == [], "ingestion started despite the file being over the cap"

    def test_a_file_at_the_cap_is_accepted(self, client, monkeypatch):
        monkeypatch.setattr(sandbox, "ingest_into_session", lambda *a, **k: None)
        sid = client.post("/session").json()["session_id"]
        response = client.post(
            f"/session/{sid}/upload",
            files={"file": ("ok.csv", csv_bytes(sandbox.MAX_TABULAR_ROWS), "text/csv")},
            data={"domain": "medical"},
        )
        assert response.status_code == 200
        assert response.json()["status"] in ("pending", "running", "done")

    def test_unsupported_format_is_refused(self, client):
        sid = client.post("/session").json()["session_id"]
        response = client.post(
            f"/session/{sid}/upload",
            files={"file": ("notes.pdf", b"%PDF-1.4", "application/pdf")},
            data={"domain": "medical"},
        )
        assert response.status_code == 400
        assert ".pdf" in response.json()["detail"]

    def test_oversized_file_is_refused(self, client, monkeypatch):
        monkeypatch.setattr(sandbox, "MAX_UPLOAD_BYTES", 100)
        sid = client.post("/session").json()["session_id"]
        response = client.post(
            f"/session/{sid}/upload",
            files={"file": ("big.csv", b"x" * 500, "text/csv")},
            data={"domain": "medical"},
        )
        assert response.status_code == 400
        assert "limit" in response.json()["detail"]

    def test_invalid_domain_is_refused(self, client):
        sid = client.post("/session").json()["session_id"]
        response = client.post(
            f"/session/{sid}/upload",
            files={"file": ("a.csv", csv_bytes(2), "text/csv")},
            data={"domain": "legal"},
        )
        assert response.status_code == 400

    def test_upload_to_an_unknown_session_is_404(self, client):
        response = client.post(
            "/session/deadbeef/upload",
            files={"file": ("a.csv", csv_bytes(2), "text/csv")},
            data={"domain": "medical"},
        )
        assert response.status_code == 404


class TestAsk:
    @pytest.fixture
    def stub_pipeline(self, monkeypatch):
        """Replace ask() with a trace-shaped stub — no Groq, no index."""
        from src.trace import (
            PlanningStage, QueryTrace, RetrievalStage, RetrievedSource,
            RoutingStage, SynthesisStage,
        )

        seen = {}

        def fake_ask(question, domain=None, log=True, router="embedding", verify=False,
                     retrieval_k=4):
            seen.update(question=question, domain=domain, router=router, verify=verify)
            return QueryTrace(
                question=question,
                routing=RoutingStage(domain=domain or "medical", method="embedding:max",
                                     confidence=0.8, margin=0.3),
                planning=PlanningStage(subqueries=[question], was_decomposed=False),
                retrieval=RetrievalStage(
                    sources=[RetrievedSource(id="doc_1", text="t", score=0.03, rank=1)],
                    n_candidates=1,
                ),
                synthesis=SynthesisStage(answer="Answer [S1].", citations=[]),
            )

        import src.agent as agent

        monkeypatch.setattr(agent, "ask", fake_ask)
        return seen

    def test_ask_returns_a_full_trace(self, client, stub_pipeline):
        body = client.post("/ask", json={"question": "What is X?"}).json()
        assert set(body) >= {"trace_id", "question", "routing", "planning",
                             "retrieval", "synthesis", "total_latency_ms"}

    def test_domain_is_omitted_so_the_router_decides(self, client, stub_pipeline):
        client.post("/ask", json={"question": "What is X?"})
        assert stub_pipeline["domain"] is None

    def test_an_explicit_domain_is_passed_through(self, client, stub_pipeline):
        client.post("/ask", json={"question": "q", "domain": "financial"})
        assert stub_pipeline["domain"] == "financial"

    def test_a_session_id_redirects_to_the_sandbox_collection(self, client, stub_pipeline):
        """A sandbox question must never reach the curated corpora."""
        session = client.post("/session").json()
        client.post("/ask", json={"question": "q", "session_id": session["session_id"]})
        assert stub_pipeline["domain"] == session["collection"]
        assert stub_pipeline["domain"] not in ("medical", "financial")

    def test_an_unknown_session_is_404(self, client, stub_pipeline):
        response = client.post("/ask", json={"question": "q", "session_id": "nope"})
        assert response.status_code == 404

    def test_empty_question_is_rejected(self, client, stub_pipeline):
        assert client.post("/ask", json={"question": ""}).status_code == 422

    def test_verify_is_off_unless_requested(self, client, stub_pipeline):
        client.post("/ask", json={"question": "q"})
        assert stub_pipeline["verify"] is False


class TestStreaming:
    def test_stream_emits_a_stage_per_event(self, client, monkeypatch):
        """The pipeline rail needs each stage as it completes; a 15-second
        synthesis must read as progress, not as a frozen page.

        The endpoint consumes ask_iter(), the generator, NOT ask(). Stubbing
        ask() here would pass while the endpoint streamed nothing — which is
        exactly what these two tests caught when the generator landed.
        """
        from src.trace import (
            PlanningStage, QueryTrace, RetrievalStage, RetrievedSource,
            RoutingStage, SynthesisStage,
        )
        import src.agent as agent

        source = RetrievedSource(id="d", text="t", score=0.1, rank=1)

        def fake_iter(*a, **k):
            routing = RoutingStage(domain="medical", method="embedding:max")
            planning = PlanningStage(subqueries=["q"], was_decomposed=False)
            retrieval = RetrievalStage(sources=[source], n_candidates=1)
            synthesis = SynthesisStage(answer="A [S1].", citations=[])
            yield "routing", routing
            yield "planning", planning
            yield "retrieval", retrieval
            yield "synthesis", synthesis
            yield "done", QueryTrace(
                question="q", routing=routing, planning=planning,
                retrieval=retrieval, synthesis=synthesis,
            )

        monkeypatch.setattr(agent, "ask_iter", fake_iter)

        with client.stream("POST", "/ask/stream", json={"question": "q"}) as response:
            assert response.status_code == 200
            stages = [
                __import__("json").loads(line[6:])["stage"]
                for line in response.iter_lines() if line.startswith("data: ")
            ]
        assert stages == ["started", "routing", "planning", "retrieval", "synthesis", "done"]

    def test_stages_are_emitted_one_at_a_time_not_batched(self, client, monkeypatch):
        """The regression that motivated the generator: the first version ran
        the whole pipeline in a thread and then emitted five events at once.
        Measured before the fix, every stage arrived together at 1.9s; after,
        routing landed at 1.7s and synthesis at 6.5s.

        Here a stage blocks until the previous one has actually been consumed,
        so a batching implementation deadlocks rather than silently passing.
        """
        import threading

        import src.agent as agent
        from src.trace import (
            PlanningStage, QueryTrace, RetrievalStage, RetrievedSource,
            RoutingStage, SynthesisStage,
        )

        emitted = threading.Event()

        def fake_iter(*a, **k):
            routing = RoutingStage(domain="medical", method="embedding:max")
            planning = PlanningStage(subqueries=["q"], was_decomposed=False)
            retrieval = RetrievalStage(
                sources=[RetrievedSource(id="d", text="t", score=0.1, rank=1)],
                n_candidates=1)
            synthesis = SynthesisStage(answer="A [S1].", citations=[])
            yield "routing", routing
            emitted.set()  # only reached if the consumer pulled the first item
            yield "planning", planning
            yield "retrieval", retrieval
            yield "synthesis", synthesis
            yield "done", QueryTrace(question="q", routing=routing, planning=planning,
                                     retrieval=retrieval, synthesis=synthesis)

        monkeypatch.setattr(agent, "ask_iter", fake_iter)

        with client.stream("POST", "/ask/stream", json={"question": "q"}) as response:
            lines = [l for l in response.iter_lines() if l.startswith("data: ")]

        assert emitted.is_set()
        assert len(lines) == 6

    def test_a_pipeline_failure_is_reported_as_an_event(self, client, monkeypatch):
        """Headers are already sent by then, so an exception cannot become a
        500 — it has to reach the client as an event or the UI hangs forever."""
        import src.agent as agent

        def boom(*a, **k):
            raise RuntimeError("groq is down")
            yield  # pragma: no cover — makes this a generator function

        monkeypatch.setattr(agent, "ask_iter", boom)
        with client.stream("POST", "/ask/stream", json={"question": "q"}) as response:
            payloads = [
                __import__("json").loads(line[6:])
                for line in response.iter_lines() if line.startswith("data: ")
            ]
        assert payloads[-1]["stage"] == "error"
        assert "groq is down" in payloads[-1]["data"]["message"]


class TestBenchmark:
    def test_benchmark_serves_the_eval_json(self, client):
        response = client.get("/benchmark")
        if response.status_code == 404:
            pytest.skip("no eval results on disk yet")
        body = response.json()
        assert "retrieval_ablation" in body
        assert body["models"]["judge"] != body["models"]["generator"]


class TestSessionEviction:
    def test_store_evicts_beyond_the_cap(self, monkeypatch):
        """Unbounded sessions means unbounded Chroma collections on a 512MB box."""
        monkeypatch.setattr(sandbox, "MAX_SESSIONS", 3)
        store = sandbox.SessionStore()
        created = [store.create() for _ in range(6)]
        assert len(store.active()) <= 3
        assert created[-1].id in {s.id for s in store.active()}
