"""
Disk cache for LLM responses. Build this before the eval harness, not after.

--- The arithmetic that makes this the highest-leverage file in Phase 6 ---

Per golden-set question, the full pipeline costs:

    1 route (LLM router only) + 1 decompose + 1 synthesis
  + 1 claim extraction + ~4 per-claim verifications          ~= 8 calls

Thirty questions is ~240 calls for ONE pass. The naive-vs-agentic ablation adds
a second pass. And nobody gets an eval harness right on the first run — you
will run it five or six times while debugging the metrics code, the golden set
format, the report rendering.

That is 1,500+ calls against a free tier with a per-day cap, and the failure
mode is brutal: you exhaust the day's quota debugging a formatting bug, and the
phase stalls until UTC midnight.

With this cache, the SECOND run onward costs zero. Only genuinely new
(model, prompt, temperature) combinations hit the network. Debugging the
report renderer becomes free.

--- Why it is safe to cache ---

Every LLM call in this project runs at temperature 0 or 0.2, and the eval
harness needs REPRODUCIBILITY anyway: an eval whose numbers move between runs
because the model felt different today is not measuring the system. Caching
makes the eval deterministic, which is a feature, not a compromise.

The key includes the model id, so switching generator or judge invalidates
correctly rather than silently serving another model's answers.

--- What it does not do ---

It is not an application cache. The live API should NOT use it: two users
asking the same question deserve fresh answers, and a stale cache entry is
worse than a slow one. It is enabled explicitly by the eval harness.
"""
import hashlib
import json
import os
import threading
import time
from pathlib import Path

CACHE_DIR = Path(os.getenv("LLM_CACHE_DIR", ".llm_cache"))

_enabled = False
_lock = threading.Lock()
_stats = {"hits": 0, "misses": 0}


def enable(cache_dir: Path | None = None) -> None:
    """Turn caching on. Off by default — only the eval harness enables it."""
    global _enabled, CACHE_DIR
    if cache_dir is not None:
        CACHE_DIR = Path(cache_dir)
    _enabled = True
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def disable() -> None:
    global _enabled
    _enabled = False


def is_enabled() -> bool:
    return _enabled


def stats() -> dict:
    """Hits, misses, and the API calls the cache saved this session."""
    total = _stats["hits"] + _stats["misses"]
    return {
        **_stats,
        "total": total,
        "hit_rate": round(_stats["hits"] / total, 3) if total else 0.0,
    }


def reset_stats() -> None:
    _stats["hits"] = _stats["misses"] = 0


def _key(model: str, prompt: str, temperature: float) -> str:
    """Content hash of everything that can change the response.

    Model id is included deliberately: switching the judge from gpt-oss to qwen
    must miss the cache, not silently serve the previous judge's verdicts.
    """
    payload = json.dumps(
        {"model": model, "prompt": prompt, "temperature": temperature},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.blake2s(payload.encode("utf-8"), digest_size=16).hexdigest()


def _path(key: str) -> Path:
    # Two-character shard, so a few thousand entries do not land in one
    # directory that Explorer refuses to open.
    return CACHE_DIR / key[:2] / f"{key}.json"


def get(model: str, prompt: str, temperature: float) -> str | None:
    if not _enabled:
        return None
    path = _path(_key(model, prompt, temperature))
    if not path.exists():
        with _lock:
            _stats["misses"] += 1
        return None
    try:
        content = json.loads(path.read_text(encoding="utf-8"))["response"]
    except (json.JSONDecodeError, KeyError, OSError):
        # A corrupt entry (interrupted write) must not break the run.
        with _lock:
            _stats["misses"] += 1
        return None
    with _lock:
        _stats["hits"] += 1
    return content


def put(model: str, prompt: str, temperature: float, response: str) -> None:
    if not _enabled:
        return
    path = _path(_key(model, prompt, temperature))
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file then rename: an interrupted run must not leave a
    # half-written entry that later reads as a valid cache hit.
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {"model": model, "temperature": temperature, "prompt": prompt, "response": response},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    tmp.replace(path)


# Transient failures worth retrying: a timed-out TLS handshake, a dropped
# connection, a 429. Matched by class NAME so this module does not have to
# import groq's exception hierarchy just to catch it.
_RETRYABLE = ("APITimeoutError", "APIConnectionError", "RateLimitError",
              "InternalServerError", "APIStatusError", "ConnectTimeout",
              "ReadTimeout", "ConnectError")

MAX_ATTEMPTS = 4
BACKOFF_BASE_S = 2.0


def _is_retryable(exc: BaseException) -> bool:
    names = {cls.__name__ for cls in type(exc).__mro__}
    return bool(names & set(_RETRYABLE))


def cached_completion(client, model: str, prompt: str, temperature: float) -> str:
    """Single entry point every LLM call in this project routes through.

    Returns the response text, from disk when available.

    Retries transient failures with exponential backoff. This is not
    defensive padding: a full eval run is ~300 calls over several minutes, and
    one timed-out TLS handshake at call 200 previously discarded every result
    computed up to that point. Because successful calls are already cached, a
    retry costs nothing and a re-run resumes from where it stopped.
    """
    hit = get(model, prompt, temperature)
    if hit is not None:
        return hit

    last: BaseException | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            )
            text = response.choices[0].message.content.strip()
            put(model, prompt, temperature, text)
            return text
        except Exception as exc:  # noqa: BLE001 — re-raised below if not transient
            if not _is_retryable(exc) or attempt == MAX_ATTEMPTS - 1:
                raise
            last = exc
            time.sleep(BACKOFF_BASE_S * (2 ** attempt))

    raise RuntimeError(f"unreachable: {last}")  # pragma: no cover
