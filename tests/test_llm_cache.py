"""LLM response cache — the thing that protects the Groq daily quota.

Measured on one verified question: 87,296 ms and 15 API calls cold, 62 ms and
ZERO calls warm. Thirty golden-set questions across two ablation passes is
~900 calls per eval run, and nobody gets an eval harness right on the first
try — so without this, debugging the report renderer burns a day's quota.

The two properties that matter:
  1. a repeat call must not reach the network
  2. anything that could change the answer must MISS, especially the model id —
     silently serving the generator's output as the judge's verdict would
     invalidate the entire faithfulness result while looking perfectly fine
"""
import pytest

from src import llm_cache


class FakeClient:
    """Counts network calls and returns a distinct response each time, so a
    stale hit is visible rather than indistinguishable from a fresh call."""

    def __init__(self):
        self.calls = 0
        outer = self

        class Completions:
            @staticmethod
            def create(model, messages, temperature):
                outer.calls += 1

                class Msg:
                    content = f"response #{outer.calls}"

                class Choice:
                    message = Msg()

                class Resp:
                    choices = [Choice()]

                return Resp()

        class Chat:
            completions = Completions()

        self.chat = Chat()


@pytest.fixture
def cache(tmp_path):
    llm_cache.enable(tmp_path / "cache")
    llm_cache.reset_stats()
    yield llm_cache
    llm_cache.disable()
    llm_cache.reset_stats()


@pytest.fixture
def client():
    return FakeClient()


class TestCaching:
    def test_a_repeat_call_does_not_reach_the_network(self, cache, client):
        first = llm_cache.cached_completion(client, "m", "prompt", 0.0)
        second = llm_cache.cached_completion(client, "m", "prompt", 0.0)
        assert first == second == "response #1"
        assert client.calls == 1

    def test_a_different_prompt_misses(self, cache, client):
        llm_cache.cached_completion(client, "m", "prompt A", 0.0)
        llm_cache.cached_completion(client, "m", "prompt B", 0.0)
        assert client.calls == 2

    def test_a_different_model_misses(self, cache, client):
        """The important one. The judge and the generator run the SAME
        verification prompts in the eval. If the model id were not in the key,
        switching judges would silently replay the generator's verdicts and the
        faithfulness number would be meaningless while looking correct."""
        llm_cache.cached_completion(client, "openai/gpt-oss-20b", "prompt", 0.0)
        llm_cache.cached_completion(client, "qwen/qwen3.8-27b", "prompt", 0.0)
        assert client.calls == 2

    def test_a_different_temperature_misses(self, cache, client):
        llm_cache.cached_completion(client, "m", "prompt", 0.0)
        llm_cache.cached_completion(client, "m", "prompt", 0.2)
        assert client.calls == 2

    def test_unicode_prompts_round_trip(self, cache, client):
        """Every prompt in this project carries LLM-written typography."""
        prompt = "Sample TC‑014 scored 0.87 — “robust”."
        llm_cache.cached_completion(client, "m", prompt, 0.0)
        assert llm_cache.cached_completion(client, "m", prompt, 0.0) == "response #1"
        assert client.calls == 1

    def test_cache_survives_a_new_process(self, tmp_path, client):
        """It is a DISK cache — that is the entire point. An in-memory one
        would be empty on every harness run."""
        llm_cache.enable(tmp_path / "cache")
        llm_cache.cached_completion(client, "m", "prompt", 0.0)
        llm_cache.disable()

        llm_cache.enable(tmp_path / "cache")  # simulates a fresh run
        assert llm_cache.cached_completion(client, "m", "prompt", 0.0) == "response #1"
        assert client.calls == 1
        llm_cache.disable()


class TestDisabledByDefault:
    def test_disabled_cache_always_calls_through(self, client):
        """The live API must not serve stale answers — two users asking the
        same question deserve fresh responses. Only the eval harness opts in."""
        llm_cache.disable()
        llm_cache.cached_completion(client, "m", "prompt", 0.0)
        llm_cache.cached_completion(client, "m", "prompt", 0.0)
        assert client.calls == 2

    def test_disabled_by_default(self):
        llm_cache.disable()
        assert not llm_cache.is_enabled()


class TestRobustness:
    def test_a_corrupt_entry_falls_back_to_the_network(self, cache, client, tmp_path):
        """An interrupted write must not poison the cache permanently."""
        llm_cache.cached_completion(client, "m", "prompt", 0.0)
        for entry in (tmp_path / "cache").rglob("*.json"):
            entry.write_text("{ this is not json", encoding="utf-8")

        assert llm_cache.cached_completion(client, "m", "prompt", 0.0) == "response #2"
        assert client.calls == 2

    def test_writes_are_atomic(self, cache, client, tmp_path):
        """Written to a temp file then renamed, so a killed run leaves no
        half-written entry that later reads as a valid hit."""
        llm_cache.cached_completion(client, "m", "prompt", 0.0)
        assert not list((tmp_path / "cache").rglob("*.tmp"))

    def test_entries_are_sharded(self, cache, client, tmp_path):
        """A few thousand files in one directory is a directory nobody can open."""
        for i in range(5):
            llm_cache.cached_completion(client, "m", f"prompt {i}", 0.0)
        for entry in (tmp_path / "cache").rglob("*.json"):
            assert entry.parent != tmp_path / "cache"


class TestStats:
    def test_hits_and_misses_are_counted(self, cache, client):
        llm_cache.cached_completion(client, "m", "a", 0.0)  # miss
        llm_cache.cached_completion(client, "m", "a", 0.0)  # hit
        llm_cache.cached_completion(client, "m", "b", 0.0)  # miss
        assert llm_cache.stats() == {"hits": 1, "misses": 2, "total": 3, "hit_rate": 0.333}

    def test_stats_are_safe_before_any_call(self, cache):
        assert llm_cache.stats()["hit_rate"] == 0.0


class TestEveryCallSiteIsRouted:
    def test_no_module_bypasses_the_cache(self):
        """A single unrouted call site quietly costs quota on every eval run.
        This test is the guard against one being added later."""
        import pathlib

        src = pathlib.Path(__file__).resolve().parent.parent / "src"
        offenders = [
            path.name
            for path in src.rglob("*.py")
            if path.name != "llm_cache.py"
            and "chat.completions.create" in path.read_text(encoding="utf-8")
        ]
        assert offenders == [], f"these bypass the cache: {offenders}"
