"""
Agentic layer — Groq (model from config.LLM_MODEL).

Two agents:
  1. Query planner  — decomposes complex questions into sub-questions.
  2. Synthesis agent — fuses retrieved chunks into one cited answer.

Both are domain-agnostic by design: they take a `domain` only to know which
collection to search, and never branch on its value. That is what lets a third
domain be added without touching this file.

Every call to ask() produces a QueryTrace (src/trace.py) recording what the
pipeline decided at each stage and how long each stage took, appended to
logs/traces.jsonl. That same object is the Phase 7 API response and the
Phase 8 UI's props — see src/trace.py for why it is defined exactly once.

Phase 5 inserts the domain router ahead of decompose_query(), so `domain`
becomes the router's decision rather than a caller-supplied argument.
"""
import json

from groq import Groq

from src.config import GROQ_API_KEY, LLM_MODEL
from src.domain_router import DOMAINS, route
from src.hybrid_retrieval import hybrid_search, is_warm
from src.trace import (
    PlanningStage,
    QueryTrace,
    RetrievalStage,
    RetrievedSource,
    RoutingStage,
    SynthesisStage,
    resolve_citations,
    timed,
)

client = Groq(api_key=GROQ_API_KEY)

# Cap on how many sources reach the synthesis prompt. AGENTS.md Agent 3 warns
# that past ~8 the prompt can outgrow the context window; 4 sub-queries at 4
# hits each could otherwise deliver 16.
MAX_SYNTHESIS_SOURCES = 8

DECOMPOSE_PROMPT = """You are a query planning agent. Given a user question, decide if it
needs to be broken into multiple sub-questions to be answered well.

If it's simple, return a JSON list with just the original question.
If it's complex (compares multiple entities, spans multiple categories, or has
multiple parts), break it into 2-4 focused sub-questions.

Return ONLY a JSON list of strings, nothing else. No explanation.

Question: {question}"""

SYNTHESIS_PROMPT = """Answer the user's question using ONLY the retrieved context below.
Every claim must be traceable to a specific source. Cite sources inline like [S1], [S2].
If the context doesn't fully answer the question, say plainly what's missing.

Question: {question}

Retrieved context:
{context}

Answer (with citations):"""


def decompose_query(question: str) -> list[str]:
    """Plan: one question in, 1-4 focused sub-questions out.

    AGENTS.md Agent 2 specifies at most 4 sub-queries and a never-crash
    fallback. The bound is enforced here rather than only requested in the
    prompt — a planner returning nine sub-queries would otherwise sail through
    and multiply retrieval cost silently.
    """
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": DECOMPOSE_PROMPT.format(question=question)}],
        temperature=0,
    )
    raw = response.choices[0].message.content.strip()
    try:
        subqueries = json.loads(raw)
    except json.JSONDecodeError:
        return [question]

    if not isinstance(subqueries, list):
        return [question]

    cleaned = [str(q).strip() for q in subqueries if str(q).strip()]
    return cleaned[:4] or [question]


def retrieve_for_subqueries(
    subqueries: list[str], domains: str | list[str], k: int = 4
) -> list[dict]:
    """Hybrid search per sub-query, deduplicated by document ID.

    A document found by several sub-queries keeps its best score, and the
    result is sorted by that score — so when the synthesis cut trims to
    MAX_SYNTHESIS_SOURCES it keeps the strongest hits, not whichever sub-query
    happened to run last. The previous dict-overwrite kept insertion order,
    which made the cut arbitrary.

    `domains` may be a list. When the router cannot separate the two corpora,
    both are searched and the fused scores decide — a slightly noisy answer
    beats a confident answer drawn from the wrong corpus.
    """
    if isinstance(domains, str):
        domains = [domains]

    best: dict[str, dict] = {}
    for domain in domains:
        for sq in subqueries:
            for doc in hybrid_search(sq, domain, k=k):
                doc = {**doc, "domain": domain}
                existing = best.get(doc["row_id"])
                if existing is None or doc["score"] > existing["score"]:
                    best[doc["row_id"]] = doc
    return sorted(best.values(), key=lambda d: d["score"], reverse=True)


def synthesize_answer(question: str, sources: list[RetrievedSource]) -> str:
    context = "\n\n".join(f"[S{s.rank}] ({s.id}): {s.text}" for s in sources)
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "user", "content": SYNTHESIS_PROMPT.format(question=question, context=context)}
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


def ask(
    question: str,
    domain: str | None = None,
    log: bool = True,
    router: str = "embedding",
) -> QueryTrace:
    """Run the full pipeline and return a QueryTrace.

    Args:
        domain: leave None to let the router decide — that is the point of the
            system, and what the API does. Passing one explicitly overrides the
            router, which the eval harness needs in order to measure retrieval
            independently of routing.
        router: "embedding" (default, free and calibrated), "embedding:centroid",
            or "llm". Phase 6 reports all three against the golden set.

    Returns the trace rather than a bare answer string because every consumer
    downstream — the API, the UI, the eval harness — needs the intermediate
    decisions, not only the final prose.
    """
    elapsed: dict = {}
    was_cold = not is_warm()  # capture BEFORE retrieval triggers the model load

    # --- Route ---
    if domain is not None:
        routing = RoutingStage(domain=domain, method="explicit", latency_ms=0.0)
        search_domains: str | list[str] = domain
    else:
        with timed(elapsed, "route"):
            decision = route(question, method=router)
        # Too close to call: search BOTH corpora and let RRF sort it out,
        # rather than blocking the user with a clarification prompt.
        searched_both = not decision.is_confident
        search_domains = list(DOMAINS) if searched_both else decision.domain
        routing = RoutingStage(
            domain="both" if searched_both else decision.domain,
            method=decision.method + (" (low-confidence: searched both)" if searched_both else ""),
            confidence=decision.confidence,
            margin=decision.margin,
            scores=decision.scores,
            latency_ms=elapsed["route"],
        )

    # --- Plan ---
    with timed(elapsed, "plan"):
        subqueries = decompose_query(question)
    planning = PlanningStage(
        subqueries=subqueries,
        was_decomposed=len(subqueries) > 1,
        latency_ms=elapsed["plan"],
    )

    # --- Retrieve ---
    with timed(elapsed, "retrieve"):
        candidates = retrieve_for_subqueries(subqueries, search_domains)
    sources = [
        RetrievedSource(
            id=doc["row_id"], text=doc["text"], score=doc["score"], rank=rank,
            domain=doc.get("domain", ""),
        )
        for rank, doc in enumerate(candidates[:MAX_SYNTHESIS_SOURCES], start=1)
    ]
    retrieval = RetrievalStage(
        sources=sources,
        n_candidates=len(candidates),
        latency_ms=elapsed["retrieve"],
    )

    # --- Synthesize ---
    with timed(elapsed, "synth"):
        answer = synthesize_answer(question, sources)
    synthesis = SynthesisStage(
        answer=answer,
        citations=resolve_citations(answer, sources),
        latency_ms=elapsed["synth"],
    )

    trace = QueryTrace(
        question=question,
        routing=routing,
        planning=planning,
        retrieval=retrieval,
        synthesis=synthesis,
        total_latency_ms=round(sum(elapsed.values()), 1),
        cold_start=was_cold,
    )

    if log:
        trace.append_to_log()
    return trace
