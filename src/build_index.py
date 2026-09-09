"""
Builds a hybrid retrieval index (dense + sparse) over generated narrative stories.

Dense:  sentence-transformers embeddings, stored in ChromaDB (persistent, local, free).
Sparse: BM25 over tokenized narrative text — catches exact keyword matches
        (ticker symbols, product names) that dense embeddings can miss.
"""
import pickle
from pathlib import Path

import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from src.config import CHROMA_DIR, EMBEDDING_MODEL


def build_index(stories: list[dict], dataset_name: str) -> None:
    """Build and persist both the dense (Chroma) and sparse (BM25) indexes."""
    embed_model = SentenceTransformer(EMBEDDING_MODEL)

    texts = [s["narrative"] for s in stories]
    ids = [s["row_id"] for s in stories]

    # --- Dense index ---
    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = chroma_client.get_or_create_collection(name=dataset_name)
    embeddings = embed_model.encode(texts, show_progress_bar=True).tolist()
    collection.upsert(ids=ids, embeddings=embeddings, documents=texts)

    # --- Sparse index ---
    tokenized = [t.lower().split() for t in texts]
    bm25 = BM25Okapi(tokenized)

    bm25_path = Path(CHROMA_DIR) / f"{dataset_name}_bm25.pkl"
    bm25_path.parent.mkdir(parents=True, exist_ok=True)
    with open(bm25_path, "wb") as f:
        pickle.dump({"bm25": bm25, "ids": ids, "texts": texts}, f)

    print(f"Indexed {len(stories)} stories for dataset '{dataset_name}'")
    print(f"  Dense index:  Chroma collection '{dataset_name}' at {CHROMA_DIR}")
    print(f"  Sparse index: {bm25_path}")