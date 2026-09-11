"""
Domain Router Agent — Phase 5. See docs/AGENTS.md, Agent 4.

The first thing that runs at query time: read the question, pick the corpus.
The user never selects a domain.

Two independent implementations behind one interface, because "which router?"
is a question worth ANSWERING with a number rather than asserting:

  route_llm()        one Groq call, structured output
  route_embedding()  cosine similarity against the indexed corpora, no API call

--- Why not the `instructor` library ---

TRD section 5 and AGENTS.md both specify instructor + Pydantic here. It was in
requirements.txt and imported nowhere. For a two-value enum it buys retry-on-
validation-failure, which is ~6 lines using the pattern decompose_query()
already uses — against a heavyweight dependency that wraps the Groq client and
whose Groq support has historically lagged. Dropped it; kept the retry.

--- Why confidence does NOT come from the LLM ---

Both documents specify a `confidence` float from the model and a clarification
fallback below 0.7. An LLM's self-reported confidence is not calibrated: it
reports ~0.95 for nearly everything including its mistakes, so that fallback
would essentially never fire, and a viva panel asking for a demo of it would
get silence.

The embedding router's COSINE MARGIN — how much closer the question sits to the
winning domain than to the loser — is a real measurement of the same thing. It
is what `confidence` means here, and it is what the low-confidence path keys on.

--- Why max-similarity rather than a centroid ---

A centroid assumes a domain occupies one region of embedding space. The medical
corpus contains both prose about exclusion criteria and tabular rows about
antigen assay scores; their average is a point that resembles neither. Max
similarity to any single document asks the question that actually matters —
"does this domain contain something relevant?" — and matches what retrieval
does next. Centroid scoring is kept as an option so Phase 6 can compare them.
"""
import json
from typing import Literal

import numpy as np
from pydantic import BaseModel, Field, ValidationError

from src.config import CHROMA_DIR, GROQ_API_KEY, LLM_MODEL
from src.llm_cache import cached_completion

Domain = Literal["medical", "financial"]
DOMAINS: tuple[Domain, ...] = ("medical", "financial")

# Below this cosine margin the corpora are too close to call, and the caller
# searches both.
#
# Measured, not guessed. Twelve questions against the real index:
#
#   genuinely contentless   "Show me the highest score."     margin 0.016
#                           "Which one performed best?"      margin 0.048
#   real questions          minimum observed                 margin 0.252
#                           median                           margin 0.446
#
# 0.10 sits in the empty band between those two groups with headroom on both
# sides. Re-derive it in Phase 6 against the full golden set — this is twelve
# questions, which is enough to place the threshold and not enough to defend
# a precise value.
#
# Worth recording: two questions drafted as "ambiguous" turned out not to be.
# "What is the growth trend?" (0.448) and "What are the exclusion criteria?"
# (0.281) both scored high, correctly — only one corpus discusses growth, and
# only one has exclusion criteria. A question is ambiguous relative to the
# CORPORA, not in the abstract, which is exactly why this number has to come
# from measurement.
LOW_CONFIDENCE_MARGIN = 0.10

ROUTER_PROMPT = """Classify which domain this question belongs to.

"medical"   — clinical studies, patients, samples, assays, antigens, protocols,
              screening, enrollment, dosages, lab results.
"financial" — stocks, tickers, quarters, revenue, profit, sectors, markets.

Return ONLY a JSON object, nothing else:
{{"domain": "medical" or "financial"}}

Question: {question}"""

_centroids: dict[str, np.ndarray] | None = None
_corpus_vectors: dict[str, np.ndarray] | None = None
_groq_client = None


class RoutingDecision(BaseModel):
    """Which corpus to search, and how sure we are."""

    domain: Domain
    method: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    margin: float | None = Field(
        None, description="Cosine gap between the winning and losing domain. None for the LLM router."
    )
    scores: dict[str, float] = Field(default_factory=dict)

    @property
    def is_confident(self) -> bool:
        """False when the domains are too close to call. The caller then
        searches BOTH corpora rather than blocking on a clarification prompt:
        a slightly noisy answer beats a confidently wrong one from the wrong
        corpus, and it demos far better than a dead end."""
        return self.margin is None or self.margin >= LOW_CONFIDENCE_MARGIN


class _LLMRoute(BaseModel):
    """Shape the LLM must return. Pydantic rejects anything else."""

    domain: Domain


def _client():
    global _groq_client
    if _groq_client is None:
        from groq import Groq

        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


def _load_corpus_vectors() -> dict[str, np.ndarray]:
    """Every indexed document's embedding, per domain, L2-normalized.

    Read straight from Chroma, so the router is always scoring against exactly
    what retrieval will search — no second copy to drift out of sync.
    """
    global _corpus_vectors
    if _corpus_vectors is not None:
        return _corpus_vectors

    import chromadb

    client = chromadb.PersistentClient(path=CHROMA_DIR)
    available = {c.name for c in client.list_collections()}

    vectors: dict[str, np.ndarray] = {}
    for domain in DOMAINS:
        if domain not in available:
            continue
        got = client.get_collection(domain).get(include=["embeddings"])
        embeddings = np.asarray(got["embeddings"], dtype=np.float32)
        if embeddings.size == 0:
            continue
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        vectors[domain] = embeddings / np.clip(norms, 1e-12, None)

    _corpus_vectors = vectors
    return vectors


def _load_centroids() -> dict[str, np.ndarray]:
    global _centroids
    if _centroids is None:
        _centroids = {}
        for domain, vectors in _load_corpus_vectors().items():
            centroid = vectors.mean(axis=0)
            _centroids[domain] = centroid / max(float(np.linalg.norm(centroid)), 1e-12)
    return _centroids


def refresh_caches() -> None:
    """Drop cached vectors so a rebuilt index is picked up without a restart."""
    global _centroids, _corpus_vectors
    _centroids = None
    _corpus_vectors = None


def route_embedding(question: str, scoring: str = "max") -> RoutingDecision:
    """Route by cosine similarity. Zero API calls, ~15ms, deterministic.

    scoring="max"      similarity to the single closest document in each domain
    scoring="centroid" similarity to each domain's mean vector
    """
    from src.hybrid_retrieval import _get_embed_model

    query = _get_embed_model().encode([question])[0].astype(np.float32)
    query = query / max(float(np.linalg.norm(query)), 1e-12)

    if scoring == "centroid":
        scores = {d: float(query @ c) for d, c in _load_centroids().items()}
    else:
        scores = {d: float((vectors @ query).max()) for d, vectors in _load_corpus_vectors().items()}

    if not scores:
        raise RuntimeError(
            "No indexed corpora to route against. Run `python -m src.main setup` first."
        )

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    winner, top = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0

    return RoutingDecision(
        domain=winner,
        method=f"embedding:{scoring}",
        # Cosine sits in [-1, 1]; map to [0, 1] so `confidence` reads the way a
        # reader expects. The MARGIN is the honest signal — see the module docstring.
        confidence=max(0.0, min(1.0, (top + 1) / 2)),
        margin=round(top - runner_up, 4),
        scores={d: round(s, 4) for d, s in scores.items()},
    )


def route_llm(question: str, retries: int = 1) -> RoutingDecision:
    """Route with one Groq call. Plain Pydantic validation plus a retry —
    no `instructor` dependency for a two-value enum."""
    last_error = None
    for _ in range(retries + 1):
        raw = cached_completion(
            _client(), LLM_MODEL, ROUTER_PROMPT.format(question=question), temperature=0
        )
        try:
            start, end = raw.index("{"), raw.rindex("}") + 1
            parsed = _LLMRoute.model_validate(json.loads(raw[start:end]))
            return RoutingDecision(
                domain=parsed.domain,
                method="llm",
                # No margin: the model does not expose a calibrated one, and
                # asking it to invent a float would be worse than admitting that.
                confidence=1.0,
                margin=None,
            )
        except (ValueError, ValidationError) as exc:
            last_error = exc

    raise ValueError(f"Router returned unusable output after {retries + 1} attempts: {last_error}")


def route(question: str, method: str = "embedding") -> RoutingDecision:
    """Route a question to a domain.

    Default is the embedding router: free, ~15ms, deterministic, and the only
    one of the two that produces a calibrated confidence signal. Phase 6
    reports both against the golden set.
    """
    if method == "llm":
        return route_llm(question)
    if method.startswith("embedding"):
        _, _, scoring = method.partition(":")
        return route_embedding(question, scoring=scoring or "max")
    raise ValueError(f"Unknown routing method: {method!r}. Use 'embedding', "
                     f"'embedding:centroid' or 'llm'.")
