"""
Hybrid retrieval: fuses dense (Chroma) and sparse (BM25) results using
Reciprocal Rank Fusion (RRF) — the same fusion method used in production
search systems.

Both backends are cached at module level. Without that, one question with 4
sub-queries costs 8 retrieval calls, each previously constructing a fresh
Chroma client and re-reading the BM25 corpus from disk. That is invisible on
a laptop and very visible against the 8s end-to-end budget in TRD section 7
on a small cloud instance.
"""
import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from src.build_index import load_bm25, tokenize_for_bm25
from src.config import CHROMA_DIR, EMBEDDING_MODEL

_embed_model = None
_chroma_client = None
_bm25_cache: dict[str, tuple[BM25Okapi, list[str], list[str]]] = {}


def _get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embed_model


def _get_chroma_client() -> chromadb.ClientAPI:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    return _chroma_client


def _get_bm25(dataset_name: str) -> tuple[BM25Okapi, list[str], list[str]]:
    if dataset_name not in _bm25_cache:
        _bm25_cache[dataset_name] = load_bm25(dataset_name)
    return _bm25_cache[dataset_name]


def refresh_caches() -> None:
    """Drop cached backends so a rebuilt index is picked up without a restart.

    Call this after build_index() inside a long-lived process (the Streamlit
    app, or an eval harness that re-indexes between runs).
    """
    global _chroma_client
    _chroma_client = None
    _bm25_cache.clear()


def dense_search(query: str, dataset_name: str, k: int = 10) -> list[tuple[str, str]]:
    collection = _get_chroma_client().get_collection(dataset_name)
    q_emb = _get_embed_model().encode([query]).tolist()
    results = collection.query(query_embeddings=q_emb, n_results=k)
    return list(zip(results["ids"][0], results["documents"][0]))


def sparse_search(query: str, dataset_name: str, k: int = 10) -> list[tuple[str, str]]:
    bm25, ids, texts = _get_bm25(dataset_name)
    # Same tokenizer as indexing — see build_index.tokenize_for_bm25. If these
    # ever diverge, sparse silently returns nothing and hybrid degrades to
    # dense-only without erroring.
    scores = bm25.get_scores(tokenize_for_bm25(query))
    ranked = sorted(zip(ids, texts, scores), key=lambda x: x[2], reverse=True)[:k]
    return [(doc_id, text) for doc_id, text, _ in ranked]


def hybrid_search(query: str, dataset_name: str, k: int = 5, rrf_k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion of dense + sparse results.

    RRF score for a doc = sum over each ranking of 1 / (rrf_k + rank + 1).
    Docs that rank well in BOTH dense and sparse search rise to the top.
    """
    dense = dense_search(query, dataset_name)
    sparse = sparse_search(query, dataset_name)

    scores: dict[str, float] = {}
    docs: dict[str, str] = {}

    for rank, (doc_id, text) in enumerate(dense):
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (rrf_k + rank + 1)
        docs[doc_id] = text
    for rank, (doc_id, text) in enumerate(sparse):
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (rrf_k + rank + 1)
        docs[doc_id] = text

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]
    return [{"row_id": doc_id, "text": docs[doc_id], "score": round(score, 4)} for doc_id, score in fused]
