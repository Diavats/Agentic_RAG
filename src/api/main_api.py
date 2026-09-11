"""
FastAPI backend — Phase 7. Implements TRD section 6, plus the upload sandbox.

    venv/Scripts/python.exe -m uvicorn src.api.main_api:app --reload

--- Two things that decide whether the deployed demo works ---

1. STARTUP PRELOAD. The first hybrid_search() in a fresh process takes ~19.8s
   loading the embedding model; the second takes 37ms. Render's free tier
   sleeps after ~15 minutes, so without preloading, the first person to open
   the link after a quiet period waits twenty seconds for their first question
   — usually while a viva panel watches. warm_up() moves that into boot.

2. INDEX REBUILD AT STARTUP. The built index is not in version control (Chroma
   writes to its files on read, so every query produced a spurious diff). The
   committed unit store is, and rebuilding from it costs zero API calls, so the
   container reconstructs its own index rather than shipping one.

--- Why /ask streams ---

The pipeline has four stages taking 2-20s in total. Returning only the final
answer means a blank screen for that whole time. Server-sent events push each
stage as it completes, so the UI's pipeline rail lights up progressively — and
a slow synthesis looks like progress rather than a hang.
"""
import asyncio
import json
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api import sessions as sandbox
from src.config import EMBEDDING_MODEL, LLM_MODEL, VERIFIER_MODEL

BENCHMARK_PATH = Path("docs/eval_results.json")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.build_index import ensure_index
    from src.hybrid_retrieval import warm_up

    built = await asyncio.to_thread(ensure_index)
    print(f"index ready: {built}")
    await asyncio.to_thread(warm_up)
    print("embedding model warm — first request will not pay the ~20s load")
    yield


app = FastAPI(
    title="PRISM — domain-agnostic agentic RAG",
    description="One pipeline, two domains, two formats. See /docs.",
    version="1.0.0",
    lifespan=lifespan,
)

# The frontend is deployed separately (Vercel), so it is cross-origin by
# construction. No credentials are used, so a permissive origin list is the
# honest configuration rather than a lazy one.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    domain: str | None = Field(
        None, description="Override the router. Omit it — deciding is the system's job."
    )
    router: str = "embedding"
    verify: bool = Field(False, description="Run the groundedness self-check (slower).")
    session_id: str | None = Field(
        None, description="Search an upload sandbox instead of the curated corpora."
    )


@app.get("/health")
def health() -> dict:
    from src.hybrid_retrieval import is_warm

    return {
        "status": "ok",
        "warm": is_warm(),
        "models": {"generator": LLM_MODEL, "judge": VERIFIER_MODEL,
                   "embeddings": EMBEDDING_MODEL},
    }


@app.get("/benchmark")
def benchmark() -> dict:
    """Static eval numbers for the UI's benchmark panel.

    Deliberately separate from /ask: these describe the SYSTEM, measured once
    against a frozen golden set. Showing them beside a single answer would
    imply that answer scored them.
    """
    if not BENCHMARK_PATH.exists():
        raise HTTPException(404, "No eval results. Run `python -m src.eval.run_eval`.")
    return json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))


def _resolve_domain(request: AskRequest) -> str | None:
    """Which collection to search: a sandbox session, an explicit override, or
    None to let the router decide.

    Shared by both /ask endpoints so an unknown session cannot return 404 on one
    and 500 on the other — which it did, because the lookup sat outside the
    try block.
    """
    if not request.session_id:
        return request.domain
    try:
        return sandbox.STORE.get(request.session_id).collection
    except sandbox.SandboxError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/ask")
def ask_endpoint(request: AskRequest) -> dict:
    """Full pipeline, one JSON response. The complete QueryTrace."""
    from src.agent import ask

    trace = ask(
        request.question,
        domain=_resolve_domain(request),
        router=request.router,
        verify=request.verify,
    )
    return trace.model_dump()


@app.post("/ask/stream")
async def ask_stream(request: AskRequest) -> StreamingResponse:
    """Same pipeline, streamed stage by stage as server-sent events.

    Each event is {"stage": ..., "data": ...}. The UI lights up its pipeline
    rail on each one, so a 15-second synthesis reads as progress rather than a
    frozen page.
    """
    from src.agent import ask_iter

    # Resolved BEFORE the stream opens, so a bad session id is a clean 404
    # rather than an error event on a 200 response.
    domain = _resolve_domain(request)

    async def events():
        yield _sse("started", {"question": request.question})

        # The pipeline is synchronous and blocking. Running it in a worker
        # thread that pushes each finished stage onto a queue is what makes
        # this actually stream: the client sees "routing done" while synthesis
        # is still running. Draining a generator with to_thread(next, ...) would
        # work too, but a queue keeps the producer running uninterrupted between
        # stages rather than re-entering it per item.
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def produce():
            try:
                for stage, payload in ask_iter(
                    request.question, domain, True, request.router, request.verify
                ):
                    loop.call_soon_threadsafe(queue.put_nowait, (stage, payload))
            except Exception as exc:  # noqa: BLE001 — delivered as an event
                loop.call_soon_threadsafe(
                    queue.put_nowait, ("error", {"message": f"{type(exc).__name__}: {exc}"})
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        task = asyncio.create_task(asyncio.to_thread(produce))
        try:
            while (item := await queue.get()) is not None:
                stage, payload = item
                data = payload if isinstance(payload, dict) else payload.model_dump()
                yield _sse(stage, data)
        finally:
            await task

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(stage: str, data: dict) -> str:
    return f"data: {json.dumps({'stage': stage, 'data': data}, ensure_ascii=False)}\n\n"


# --------------------------------------------------------------------------
# Upload sandbox
# --------------------------------------------------------------------------

@app.post("/session")
def create_session() -> dict:
    return sandbox.STORE.create().as_dict()


@app.get("/session/{session_id}")
def get_session(session_id: str) -> dict:
    try:
        return sandbox.STORE.get(session_id).as_dict()
    except sandbox.SandboxError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.delete("/session/{session_id}")
def delete_session(session_id: str) -> dict:
    sandbox.STORE.drop(session_id)
    return {"deleted": session_id}


@app.post("/session/{session_id}/upload")
async def upload(
    session_id: str,
    file: UploadFile = File(...),
    domain: str = Form("medical"),
) -> dict:
    """Accept one file into the session's own collection.

    Returns immediately with a job id. Ingestion runs in the background because
    a tabular file costs one LLM call per row, and a request blocking on 25
    sequential API calls times out behind any proxy.
    """
    try:
        session = sandbox.STORE.get(session_id)
    except sandbox.SandboxError as exc:
        raise HTTPException(404, str(exc)) from exc

    if domain not in ("medical", "financial"):
        raise HTTPException(400, "domain must be 'medical' or 'financial'")

    payload = await file.read()
    try:
        suffix = sandbox.validate_upload(file.filename or "", len(payload))
    except sandbox.SandboxError as exc:
        raise HTTPException(400, str(exc)) from exc

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"prism_{session_id}_"))
    path = tmp_dir / (file.filename or f"upload{suffix}")
    path.write_bytes(payload)

    # Reject an oversized tabular file BEFORE starting the job, so the user
    # gets the refusal as an HTTP error rather than having to poll for it.
    if suffix in sandbox.TABULAR_SUFFIXES:
        try:
            sandbox.check_row_cap(sandbox.count_rows(path))
        except sandbox.SandboxError as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise HTTPException(413, str(exc)) from exc

    job = sandbox.Job(id=f"job_{len(session.jobs) + 1}")
    session.jobs[job.id] = job

    async def run():
        try:
            await asyncio.to_thread(sandbox.ingest_into_session, session, path, domain, job)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    asyncio.create_task(run())
    return {"session_id": session_id, **job.as_dict()}


@app.get("/session/{session_id}/job/{job_id}")
def job_status(session_id: str, job_id: str) -> dict:
    try:
        session = sandbox.STORE.get(session_id)
    except sandbox.SandboxError as exc:
        raise HTTPException(404, str(exc)) from exc
    job = session.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"No job {job_id} in session {session_id}")
    return job.as_dict()


@app.get("/limits")
def limits() -> dict:
    """What the sandbox will and will not accept, so the UI can say so up front
    rather than after a failed upload."""
    return {
        "max_tabular_rows": sandbox.MAX_TABULAR_ROWS,
        "max_upload_bytes": sandbox.MAX_UPLOAD_BYTES,
        "session_ttl_seconds": sandbox.SESSION_TTL_SECONDS,
        "supported_formats": sorted(sandbox.TABULAR_SUFFIXES | sandbox.TEXTUAL_SUFFIXES),
        "why_row_cap": (
            "Each tabular row costs one LLM call to turn into a narrative, so an "
            "unbounded upload would exhaust a shared daily quota."
        ),
    }
