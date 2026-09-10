"""
Groundedness self-check — Phase 5.5.

After synthesis, split the answer into atomic claims and check each one against
the source it cites. Returns supported/total.

--- Why claim-level and not a 1-5 score ---

"Rate the faithfulness of this answer from 1 to 5" produces a number nobody can
audit. Two different judges give 3 and 4 and there is no way to adjudicate,
because the number does not decompose into anything checkable.

supported/total does decompose. If it reports 7/9, a human can read the two
unsupported claims and agree or disagree. That is the difference between a
metric and a vibe, and it is the difference between an eval a viva panel
believes and one they poke a hole in.

--- Why a different model ---

The generator writes the answer; a DIFFERENT model family grades it. Asking a
model to mark its own homework is a biased judge — it tends to rate its own
phrasing as well-supported, because the same weights produced both the claim
and the judgement. This is the single cheapest credibility fix in the project.

--- What this is NOT ---

Not an objective hallucination measurement. It is a system checking itself with
another instance of the same kind of system, and it is labelled `self-check`
everywhere it surfaces. The honest framing is worth more than the number: a
project that calls this "hallucination score: 94%" is making a claim it cannot
support, and an interviewer who has built one of these will know.

The Phase 6 eval harness uses the same function against the golden set, where
answers are additionally checked against hand-written ground truth — that is
where the defensible numbers come from. This is the live signal shown per
answer.
"""
import json
import re

from src.config import GROQ_API_KEY, VERIFIER_MODEL
from src.trace import RetrievedSource, VerificationStage, timed

_client = None

EXTRACT_PROMPT = """Break this answer into atomic factual claims.

An atomic claim states ONE fact. Split compound sentences. Keep the [S1]-style
citation markers attached to the claim they belong to. Ignore hedging,
restatements of the question, and statements about what is missing from the
context — those are not factual claims about the data.

Return ONLY a JSON list of strings. If the answer makes no factual claims
(for example it says the context does not cover the question), return [].

Answer:
{answer}"""

VERIFY_PROMPT = """Does the SOURCE support the CLAIM?

Answer with ONLY one word:
  SUPPORTED   — the source states this, or it follows directly from the source
  UNSUPPORTED — the source does not state this, contradicts it, or the claim
                adds specifics the source does not contain

CLAIM: {claim}

SOURCE:
{source}"""

CITATION_IN_CLAIM = re.compile(r"[\[【［]\s*S\s*(\d+)\s*[\]】］]", re.IGNORECASE)


def _get_client():
    global _client
    if _client is None:
        from groq import Groq

        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def _ask_judge(prompt: str, model: str) -> str:
    response = _get_client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return response.choices[0].message.content.strip()


def extract_claims(answer: str, model: str = VERIFIER_MODEL) -> list[str]:
    """Split an answer into atomic factual claims. Never raises."""
    if not answer.strip():
        return []
    raw = _ask_judge(EXTRACT_PROMPT.format(answer=answer), model)
    try:
        start, end = raw.index("["), raw.rindex("]") + 1
        claims = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError):
        return []
    if not isinstance(claims, list):
        return []
    # Cap the claim count: verification costs one call per claim, and a
    # rambling answer should not be able to spend thirty calls of rate limit.
    return [str(c).strip() for c in claims if str(c).strip()][:12]


def _sources_for_claim(claim: str, sources: list[RetrievedSource]) -> list[RetrievedSource]:
    """The sources a claim cites, or all of them if it cites none.

    An uncited claim is checked against the whole retrieved context rather than
    counted as unsupported outright: the model often states something the
    context genuinely supports without attaching a marker, and calling that a
    hallucination would make the number measure citation discipline instead of
    groundedness. Missing markers are already reported separately, as
    unresolved citations on the trace.
    """
    cited = []
    for match in CITATION_IN_CLAIM.finditer(claim):
        index = int(match.group(1)) - 1
        if 0 <= index < len(sources):
            cited.append(sources[index])
    return cited or list(sources)


def verify_answer(
    answer: str,
    sources: list[RetrievedSource],
    model: str = VERIFIER_MODEL,
) -> VerificationStage:
    """Check every claim in an answer against the sources it cites.

    Cost: 1 call to extract claims + 1 per claim. A typical answer runs 4-8
    calls, which is why the eval harness caches responses to disk.

    A correct abstention ("the context does not cover this") extracts zero
    claims and scores 1.0 — refusing to answer is perfectly grounded, and
    scoring it 0.0 would punish exactly the behaviour the system should have.
    """
    elapsed: dict = {}

    with timed(elapsed, "total"):
        claims = extract_claims(answer, model=model)

        supported = 0
        for claim in claims:
            context = "\n\n".join(
                f"[S{s.rank}] {s.text}" for s in _sources_for_claim(claim, sources)
            )
            verdict = _ask_judge(
                VERIFY_PROMPT.format(claim=claim, source=context), model
            ).upper()
            # Check UNSUPPORTED first — it contains "SUPPORTED" as a substring.
            if "UNSUPPORTED" not in verdict and "SUPPORTED" in verdict:
                supported += 1

    total = len(claims)
    return VerificationStage(
        supported_claims=supported,
        total_claims=total,
        score=1.0 if total == 0 else round(supported / total, 3),
        judge_model=model,
        latency_ms=elapsed["total"],
    )
