"""Shared fixtures.

Design rule: the default test run makes ZERO Groq API calls. Every LLM
boundary is either stubbed or marked `live`. Groq's free tier has a per-day
cap that Phase 6's eval harness will need in full, and a test suite that
quietly eats it is worse than no test suite.
"""
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: hits the real Groq API — deselected by default, run with -m live"
    )
    config.addinivalue_line(
        "markers", "model: loads the embedding model (~20s the first time)"
    )


def pytest_collection_modifyitems(config, items):
    """Skip `live` tests unless explicitly requested with `-m live`."""
    if "live" in (config.getoption("-m") or ""):
        return
    skip = pytest.mark.skip(reason="needs Groq API; run with -m live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def embed_model():
    """The real embedding model, loaded once for the whole session.

    Chunking correctness genuinely depends on this specific tokenizer, so
    stubbing it would test nothing worth testing.
    """
    from sentence_transformers import SentenceTransformer

    from src.config import EMBEDDING_MODEL

    return SentenceTransformer(EMBEDDING_MODEL)


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """Point the index at a temp directory.

    Without this, tests would upsert into the committed chroma_store/ that the
    deployed API serves. Both modules import CHROMA_DIR by value, so both need
    patching.
    """
    import src.build_index as build_index
    import src.hybrid_retrieval as hybrid_retrieval

    store = tmp_path / "chroma"
    store.mkdir()
    monkeypatch.setattr(build_index, "CHROMA_DIR", str(store))
    monkeypatch.setattr(hybrid_retrieval, "CHROMA_DIR", str(store))
    hybrid_retrieval.refresh_caches()
    yield store
    hybrid_retrieval.refresh_caches()


@pytest.fixture
def make_unit():
    """Build a KnowledgeUnit without going near an extractor or an LLM."""
    from src.schema import KnowledgeUnit, KnowledgeUnitMetadata, make_unit_id

    def _make(text, domain="financial", source_type="tabular",
              source_file="test.csv", index=0, extra=None):
        return KnowledgeUnit(
            id=make_unit_id(domain, source_type, source_file, index),
            domain=domain,
            source_type=source_type,
            text=text,
            metadata=KnowledgeUnitMetadata(source_file=source_file, extra=extra or {}),
        )

    return _make
