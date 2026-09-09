"""
Builds a hybrid retrieval index (dense + sparse) over generated narrative stories.

Dense:  sentence-transformers embeddings, stored in ChromaDB (persistent, local, free).
Sparse: BM25 over tokenized narrative text — catches exact keyword matches
        (ticker symbols, product names) that dense embeddings can miss.

--- Incremental ingestion (RULES section 3, non-negotiable 10) ---

Medical data arrives in pieces over the build period, not as one drop, so
build_index() must be safe to re-run with a new batch.

Chroma gets this for free via .upsert(). BM25 does NOT: rank-bm25 has no
incremental API — a BM25Okapi holds precomputed corpus statistics (IDF, average
document length) over a FIXED corpus, so adding a document means recomputing
them. The previous version rebuilt BM25 from only the batch passed in and
overwrote the pickle, which left the dense index holding every chunk and the
sparse index holding only the newest batch. Hybrid search still returned
plausible results, so the corpus loss was silent.

The fix is load-merge-rebuild: read what is already on disk, merge by ID, and
recompute BM25 over the union. At this corpus size (tens to low hundreds of
units) the recompute is milliseconds.

NOTE for Phase 4: this module still takes the Phase 0 ad-hoc
{row_id, narrative} dict, not a KnowledgeUnit. Reconciling that is Phase 4's
job (see the plan file, Fix 5) and includes sanitizing metadata.extra, which
carries raw pandas values (NaN, numpy.int64, Timestamp) that Chroma's
scalar-only metadata will reject.
"""
import pickle
from pathlib import Path

import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from src.config import CHROMA_DIR, EMBEDDING_MODEL


def _bm25_path(dataset_name: str) -> Path:
    return Path(CHROMA_DIR) / f"{dataset_name}_bm25.pkl"


def tokenize_for_bm25(text: str) -> list[str]:
    """Single definition of BM25 tokenization.

    It must match what hybrid_retrieval.sparse_search() applies to the query
    (`query.lower().split()`) — if indexing and querying tokenize differently,
    sparse retrieval quietly returns nothing and hybrid degrades to dense-only.
    """
    return text.lower().split()


def _load_existing(dataset_name: str) -> tuple[list[str], list[str]]:
    """Return (ids, texts) already in the sparse index, or empty lists."""
    path = _bm25_path(dataset_name)
    if not path.exists():
        return [], []
    with open(path, "rb") as f:
        data = pickle.load(f)
    return list(data.get("ids", [])), list(data.get("texts", []))


def build_index(stories: list[dict], dataset_name: str) -> None:
    """Build/extend and persist both the dense (Chroma) and sparse (BM25) indexes.

    Safe to call repeatedly with new batches: existing units are updated in
    place by ID, new ones are appended, and nothing already indexed is lost.
    """
    embed_model = SentenceTransformer(EMBEDDING_MODEL)

    texts = [s["narrative"] for s in stories]
    ids = [s["row_id"] for s in stories]

    # --- Dense index (Chroma handles the merge itself, via upsert) ---
    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = chroma_client.get_or_create_collection(name=dataset_name)
    embeddings = embed_model.encode(texts, show_progress_bar=True).tolist()
    collection.upsert(ids=ids, embeddings=embeddings, documents=texts)

    # --- Sparse index (merge by hand: rank-bm25 has no incremental API) ---
    merged: dict[str, str] = dict(zip(*_load_existing(dataset_name)))
    previously_held = len(merged)
    merged.update(zip(ids, texts))  # this batch wins on a duplicate ID

    all_ids = list(merged.keys())
    all_texts = list(merged.values())

    # Persist the CORPUS, not the fitted BM25 object. A pickled BM25Okapi
    # couples this artifact to the installed rank-bm25 and Python versions,
    # so it can fail to unpickle on a deployment host whose versions differ.
    # Refitting on load is O(n) over a few hundred short documents.
    path = _bm25_path(dataset_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump({"ids": all_ids, "texts": all_texts}, f)

    added = len(all_ids) - previously_held
    print(f"Indexed {len(stories)} stories for dataset '{dataset_name}'")
    print(f"  Dense index:  Chroma collection '{dataset_name}' at {CHROMA_DIR}")
    print(f"  Sparse index: {path}")
    print(
        f"  Corpus now {len(all_ids)} documents "
        f"({previously_held} already held, {added} new, "
        f"{len(stories) - added} updated in place)"
    )


def load_bm25(dataset_name: str) -> tuple[BM25Okapi, list[str], list[str]]:
    """Load the sparse corpus and fit BM25 over it. Used by hybrid_retrieval."""
    ids, texts = _load_existing(dataset_name)
    if not ids:
        raise FileNotFoundError(
            f"No sparse index for dataset '{dataset_name}' at "
            f"{_bm25_path(dataset_name)}. Run `python -m src.main index "
            f"--dataset-name {dataset_name}` first."
        )
    return BM25Okapi([tokenize_for_bm25(t) for t in texts]), ids, texts
