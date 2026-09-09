"""
Hybrid retrieval: fuses dense (Chroma) and sparse (BM25) results using
Reciprocal Rank Fusion (RRF) — the same fusion method used in production
search systems.
"""
import pickle
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from src.config import CHROMA_DIR, EMBEDDING_MODEL

_embed_model = None


def _get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embed_model


def dense_search(query: str, dataset_name: str, k: int = 10) -> list[tuple[str, str]]:
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(dataset_name)
    q_emb = _get_embed_model().encode([query]).tolist()
    results = collection.query(query_embeddings=q_emb, n_results=k)
    return list(zip(results["ids"][0], results["documents"][0]))


def sparse_search(query: str, dataset_name: str, k: int = 10) -> list[tuple[str, str]]:
    bm25_path = Path(CHROMA_DIR) / f"{dataset_name}_bm25.pkl"
    with open(bm25_path, "rb") as f:
        data = pickle.load(f)
    bm25, ids, texts = data["bm25"], data["ids"], data["texts"]
    scores = bm25.get_scores(query.lower().split())
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