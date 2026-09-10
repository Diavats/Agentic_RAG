"""
QueryTrace — what the system did, and how long each part of it took.

This one model is deliberately four things at once:

  1. the API response body            (Phase 7, POST /ask)
  2. the frontend's props             (Phase 8, the pipeline rail)
  3. the eval harness's per-case record (Phase 6)
  4. the debug log                    (logs/traces.jsonl, from today)

Defining it once, here, is what stops those four from each inventing their own
shape and then needing translation layers between them. It is the same
reasoning as schema.KnowledgeUnit: pick the seam deliberately, then make
everything downstream depend on the seam instead of on each other.

It also converts TRD section 7 from aspiration into measurement. That document
asserts "domain routing < 1.5s" and "end-to-end < 8s" with nothing anywhere in
the codebase recording either number. Every field below that ends in
`latency_ms` is one of those claims becoming checkable.

Stages the pipeline does not have yet (routing in Phase 5, verification in
Phase 5.5) are modelled now and left optional, so adding them later is filling
a field rather than changing a contract every consumer depends on.
"""
import json
import re
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

TRACE_LOG = Path("logs/traces.jsonl")

# The synthesis prompt numbers its context blocks [S1], [S2], ... in the order
# they were retrieved, so a marker maps back to a source by position.
#
# The bracket class is not defensive programming for its own sake. The prompt
# asks for [S1] and the model complies most of the time, but on 3 of the first
# 10 recorded traces it emitted FULLWIDTH brackets instead — 【S1】. A parser
# matching only ASCII brackets silently reported ZERO citations for those
# answers, which would have understated citation accuracy (a PRD section 7
# success metric) by roughly thirty points. Parse what the model actually
# writes, not only what it was asked to write.
CITATION_PATTERN = re.compile(
    r"[\[【［]\s*S\s*(\d+)\s*[\]】］]",
    re.IGNORECASE,
)


@contextmanager
def timed(into: dict, key: str = "latency_ms"):
    """Record wall-clock milliseconds for a block into `into[key]`.

    perf_counter, not time(): it is monotonic, so a clock adjustment mid-query
    cannot produce a negative latency.
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        into[key] = round((time.perf_counter() - start) * 1000, 1)


class RetrievedSource(BaseModel):
    """One document that made it into the synthesis prompt."""

    id: str
    text: str
    score: float = Field(..., description="RRF fusion score")
    rank: int = Field(..., description="1-based position in the fused ranking")
    source_file: str = ""
    source_type: str = ""
    domain: str = Field("", description="Which corpus this hit came from — the "
                                        "column that matters when the router "
                                        "was unsure and searched both.")


class Citation(BaseModel):
    """One [Sn] marker found in the answer, resolved back to a source.

    `resolved=False` means the model cited a source number that was never
    given to it — it wrote [S9] when only 8 blocks existed. That is a
    hallucination signal available for free, with no judge call, and it is
    exactly the kind of thing that is invisible when the answer is only ever
    read as prose.
    """

    marker: str
    source_id: str | None = None
    resolved: bool = False


class RoutingStage(BaseModel):
    """Which corpus was searched, and how that was decided.

    method="explicit" until Phase 5 — the domain came from the caller, not
    from a router. Recording that honestly now means traces captured before
    and after the router are directly comparable.
    """

    domain: str
    method: str = "explicit"
    confidence: float | None = None
    margin: float | None = Field(
        None,
        description="Cosine gap between winning and losing domain. This, not "
                    "the LLM's self-reported number, is the calibrated signal.",
    )
    scores: dict[str, float] = Field(default_factory=dict)
    latency_ms: float = 0.0


class PlanningStage(BaseModel):
    subqueries: list[str]
    was_decomposed: bool
    latency_ms: float = 0.0


class RetrievalStage(BaseModel):
    sources: list[RetrievedSource]
    n_candidates: int = Field(..., description="Unique documents before the synthesis cut")
    latency_ms: float = 0.0


class SynthesisStage(BaseModel):
    answer: str
    citations: list[Citation]
    latency_ms: float = 0.0

    @property
    def unresolved_citations(self) -> list[str]:
        return [c.marker for c in self.citations if not c.resolved]


class VerificationStage(BaseModel):
    """Populated in Phase 5.5. Claim-level, not a 1-5 vibes score.

    Surfaced to users as a SELF-CHECK, never as an objective hallucination
    measurement: a system grading its own output is a signal, and labelling it
    honestly is worth more than the number itself.
    """

    supported_claims: int
    total_claims: int
    score: float
    judge_model: str
    latency_ms: float = 0.0


class QueryTrace(BaseModel):
    trace_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    question: str
    routing: RoutingStage
    planning: PlanningStage
    retrieval: RetrievalStage
    synthesis: SynthesisStage
    verification: VerificationStage | None = None
    total_latency_ms: float = 0.0
    cold_start: bool = Field(
        False,
        description=(
            "True if the embedding model had to load during this query. A cold "
            "query spends ~20s in the retrieval stage doing work that has "
            "nothing to do with retrieval, so cold and warm traces must never "
            "be averaged together when reporting latency."
        ),
    )

    def append_to_log(self, path: Path = TRACE_LOG) -> Path:
        """One JSON object per line. Append-only, so a crashed run keeps
        everything it had already written, and Phase 6 can stream it."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(self.model_dump_json() + "\n")
        return path

    def summary(self) -> str:
        """One dense line for the CLI — the whole pipeline at a glance."""
        parts = [
            f"route={self.routing.domain}({self.routing.method}) {self.routing.latency_ms:.0f}ms",
            f"plan={len(self.planning.subqueries)}q {self.planning.latency_ms:.0f}ms",
            f"retrieve={len(self.retrieval.sources)}/{self.retrieval.n_candidates} "
            f"{self.retrieval.latency_ms:.0f}ms",
            f"synth={self.synthesis.latency_ms:.0f}ms",
        ]
        if self.verification:
            v = self.verification
            parts.append(f"verify={v.supported_claims}/{v.total_claims}")
        unresolved = self.synthesis.unresolved_citations
        if unresolved:
            parts.append(f"UNRESOLVED={','.join(unresolved)}")
        flag = " COLD" if self.cold_start else ""
        return f"[{self.total_latency_ms:.0f}ms{flag}] " + "  ".join(parts)


def resolve_citations(answer: str, sources: list[RetrievedSource]) -> list[Citation]:
    """Map every [Sn] marker in the answer back to the source it points at.

    Deduplicated and ordered by first appearance, so a source cited three
    times counts once. A marker beyond the number of supplied sources
    resolves to None and is flagged — see Citation.
    """
    citations: list[Citation] = []
    seen: set[str] = set()

    for match in CITATION_PATTERN.finditer(answer):
        marker = f"S{match.group(1)}"
        if marker in seen:
            continue
        seen.add(marker)

        index = int(match.group(1)) - 1  # [S1] is sources[0]
        in_range = 0 <= index < len(sources)
        citations.append(
            Citation(
                marker=marker,
                source_id=sources[index].id if in_range else None,
                resolved=in_range,
            )
        )

    return citations


def read_traces(path: Path = TRACE_LOG) -> list[QueryTrace]:
    """Load the trace log. Used by Phase 6 and by docs/TRACES.md generation."""
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [QueryTrace.model_validate_json(line) for line in f if line.strip()]
