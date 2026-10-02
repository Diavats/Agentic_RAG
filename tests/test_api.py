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
    # The real gate needs the real index; tests of the gate itself live in
    # TestDomainGate. Here every upload is "medical" unless a test says not.
    monkeypatch.setattr(sandbox, "guess_domain",
                        lambda path: ("medical", {"medical": 0.5, "financial": 0.1}))
    api._quota.clear()
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
    def test_root_redirects_to_docs(self, client):
        """The bare origin is the URL VSCode makes clickable in the uvicorn
        startup line. It used to 404 with {"detail":"Not Found"}, which reads
        as a broken server."""
        r = client.get("/", follow_redirects=False)
        assert r.status_code in (302, 307), r.status_code
        assert r.headers["location"] == "/docs"
        assert client.get("/").status_code == 200

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
        sandbox.STORE.get(session["session_id"]).units.append(object())
        client.post("/ask", json={"question": "q", "session_id": session["session_id"]})
        assert stub_pipeline["domain"] == session["collection"]
        assert stub_pipeline["domain"] not in ("medical", "financial")

    def test_asking_before_the_upload_finishes_is_409_not_500(self, client, stub_pipeline):
        sid = client.post("/session").json()["session_id"]
        assert client.post("/ask", json={"question": "q", "session_id": sid}).status_code == 409
        assert client.post("/ask/stream", json={"question": "q", "session_id": sid}).status_code == 409

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
        # The browser gets a plain message; the raw exception stays in the log.
        assert "groq is down" not in payloads[-1]["data"]["message"]
        assert "try again" in payloads[-1]["data"]["message"]


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


class TestUploadDomainGate:
    """The gate's HTTP behaviour, with the gate itself stubbed."""

    def _upload(self, client, domain="auto"):
        sid = client.post("/session").json()["session_id"]
        return client.post(f"/session/{sid}/upload", data={"domain": domain},
                           files={"file": ("a.csv", csv_bytes(2), "text/csv")})

    def test_auto_uses_the_guess(self, client, monkeypatch):
        monkeypatch.setattr(sandbox, "ingest_into_session", lambda *a, **k: None)
        monkeypatch.setattr(sandbox, "guess_domain", lambda p: ("financial", {"financial": 0.6}))
        body = self._upload(client).json()
        assert body["domain"] == body["guessed"] == "financial"

    def test_user_can_correct_finance_vs_medical(self, client, monkeypatch):
        monkeypatch.setattr(sandbox, "ingest_into_session", lambda *a, **k: None)
        monkeypatch.setattr(sandbox, "guess_domain", lambda p: ("financial", {"financial": 0.6}))
        body = self._upload(client, domain="medical").json()
        assert (body["domain"], body["guessed"]) == ("medical", "financial")

    def test_off_topic_is_422_and_costs_no_quota(self, client, monkeypatch):
        def refuse(path):
            raise sandbox.SandboxError("not finance or medical")
        monkeypatch.setattr(sandbox, "guess_domain", refuse)
        assert self._upload(client, domain="medical").status_code == 422
        assert client.get("/quota").json()["upload"]["left"] == 3

    def test_classify_previews_without_spending_quota(self, client):
        sid = client.post("/session").json()["session_id"]
        r = client.post(f"/session/{sid}/classify",
                        files={"file": ("a.csv", csv_bytes(2), "text/csv")})
        assert r.json()["domain"] == "medical"
        assert client.get("/quota").json()["upload"]["left"] == 3


class TestQuota:
    def test_the_16th_question_is_refused(self, client, monkeypatch):
        import src.agent as agent
        monkeypatch.setattr(agent, "ask", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stop")))
        import src.api.main_api as api
        api._quota[("testclient", "question")] = api.DAILY_LIMITS["question"]
        r = client.post("/ask", json={"question": "q"})
        assert r.status_code == 429 and "tomorrow" in r.json()["detail"]

    def test_visitors_behind_cloudflare_are_counted_separately(self, client):
        import src.api.main_api as api
        api._quota[("1.1.1.1", "question")] = api.DAILY_LIMITS["question"]
        a = client.get("/quota", headers={"cf-connecting-ip": "1.1.1.1"}).json()
        b = client.get("/quota", headers={"cf-connecting-ip": "2.2.2.2"}).json()
        assert (a["question"]["left"], b["question"]["left"]) == (0, 15)

    def test_a_forged_x_forwarded_for_does_not_reset_the_quota(self, client):
        """Measured on Render: a fake X-Forwarded-For used to get a fresh quota."""
        import src.api.main_api as api
        api._quota[("testclient", "question")] = api.DAILY_LIMITS["question"]
        r = client.get("/quota", headers={"x-forwarded-for": "9.9.9.9"}).json()
        assert r["question"]["left"] == 0

    def test_session_creation_is_capped_per_visitor(self, client):
        import src.api.main_api as api
        codes = [client.post("/session").status_code for _ in range(api.DAILY_LIMITS["session"] + 1)]
        assert codes[-1] == 429 and set(codes[:-1]) == {200}

    def test_the_browser_may_delete_a_session(self, client):
        r = client.options("/session/x", headers={
            "Origin": "https://prism.vercel.app", "Access-Control-Request-Method": "DELETE"})
        assert "DELETE" in r.headers["access-control-allow-methods"]


class TestUploadSafety:
    def test_a_path_in_the_filename_cannot_escape_the_temp_folder(self, client, monkeypatch):
        seen = {}
        monkeypatch.setattr(sandbox, "ingest_into_session",
                            lambda session, path, domain, job: seen.update(path=path))
        sid = client.post("/session").json()["session_id"]
        r = client.post(f"/session/{sid}/upload",
                        files={"file": ("../../../evil.csv", csv_bytes(2), "text/csv")})
        assert r.status_code == 200
        import time
        for _ in range(50):
            if "path" in seen:
                break
            time.sleep(0.05)
        assert seen["path"].name == "evil.csv"
        assert seen["path"].parent.name.startswith("prism_")

    def test_a_zip_bomb_is_refused_before_it_is_opened(self, client):
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("word/document.xml", b"0" * (sandbox.MAX_UNPACKED_BYTES + 1))
        assert len(buf.getvalue()) < sandbox.MAX_UPLOAD_BYTES  # small on the wire
        sid = client.post("/session").json()["session_id"]
        r = client.post(f"/session/{sid}/upload",
                        files={"file": ("bomb.docx", buf.getvalue(), "application/octet-stream")})
        assert r.status_code == 400 and "unpacks" in r.json()["detail"]
