"""
Builds a hybrid retrieval index (dense + sparse) over KnowledgeUnits — one
collection per domain.

Dense:  sentence-transformers embeddings, stored in ChromaDB (persistent, local, free).
Sparse: BM25 over tokenized text — catches exact keyword matches (ticker
        symbols, sample IDs, drug names) that dense embeddings can miss.

This module is the first consumer of the KnowledgeUnit contract, and it is
deliberately the ONLY place that knows how a KnowledgeUnit becomes an index
record. It reads `.id`, `.text`, `.domain`, `.source_type` and `.metadata` —
and nothing else. It never branches on which domain or which extractor
produced a unit. That is the whole point of the schema (TRD section 3): adding
a third domain later must not require editing this file.

--- Incremental ingestion (RULES section 3, non-negotiable 10) ---

Medical data arrives in pieces over the build period, not as one drop, so
build_index() must be safe to re-run with a new batch.

Chroma gets this for free via .upsert(). BM25 does NOT: rank-bm25 has no
incremental API — a BM25Okapi holds precomputed corpus statistics (IDF, average
document length) over a FIXED corpus, so adding a document means recomputing
them. An earlier version rebuilt BM25 from only the batch passed in and
overwrote the pickle, which left the dense index holding every unit and the
sparse index holding only the newest batch. Hybrid search still returned
plausible results, so the corpus loss was silent.

The fix is load-merge-rebuild: read what is already on disk, merge by ID, and
recompute BM25 over the union. At this corpus size (tens to low hundreds of
units) the recompute is milliseconds.
"""
import math
import pickle
import unicodedata
from datetime import date, datetime
from pathlib import Path

import chromadb
from rank_bm25 import BM25Okapi

from src.config import CHROMA_DIR
from src.schema import KnowledgeUnit

# Keys written from the KnowledgeUnit itself. metadata.extra may not overwrite
# these — a CSV with a column literally named "domain" must not be able to
# relabel which collection a unit claims to belong to.
RESERVED_METADATA_KEYS = {"domain", "source_type", "source_file", "generated_at"}


def _bm25_path(domain: str) -> Path:
    return Path(CHROMA_DIR) / f"{domain}_bm25.pkl"


# Typographic characters the narrative-generating LLM emits constantly, mapped
# to the ASCII a human actually types. NFKC alone does NOT fix these: U+2011
# (non-breaking hyphen), the curly quotes and the em dash have no compatibility
# decomposition, so they survive normalization unchanged.
_TYPOGRAPHIC_TO_ASCII = str.maketrans({
    "‐": "-", "‑": "-", "‒": "-",   # hyphens
    "–": "-", "—": "-", "―": "-",   # dashes
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    " ": " ", " ": " ", " ": " ", "​": " ",
    "…": " ",
})

_STRIP_CHARS = ".,;:!?()[]{}<>\"'`"


def normalize_for_bm25(text: str) -> str:
    """Fold Unicode typography down to what a user would type."""
    return unicodedata.normalize("NFKC", text).translate(_TYPOGRAPHIC_TO_ASCII).lower()


def tokenize_for_bm25(text: str) -> list[str]:
    """Single definition of BM25 tokenization, applied identically to indexed
    documents and to incoming queries.

    Normalization is not cosmetic here. BM25 exists in this system to catch
    EXACT matches that dense embeddings miss — ticker symbols, sample IDs.
    The narrative generator is an LLM, and it writes "TC‑014" with a
    non-breaking hyphen. A user types "TC-014". Those are different tokens, so
    the query scored 0.0000 against every document in the corpus and BM25
    contributed nothing to the fusion — silently, because RRF still returned
    a ranked list and the failure looked like ordinary ranking.

    Because build_index persists the raw corpus rather than a fitted BM25Okapi,
    changing this function takes effect on the next load_bm25() with no
    re-indexing needed.
    """
    tokens = []
    for raw in normalize_for_bm25(text).split():
        token = raw.strip(_STRIP_CHARS)
        # Require at least one alphanumeric character. A bare "---" or "..."
        # carries no meaning but still counts toward document length, which
        # BM25 uses to normalize scores — so punctuation-only tokens quietly
        # penalize documents that contain more punctuation.
        if token and any(c.isalnum() for c in token):
            tokens.append(token)
    return tokens


def _scalarize(value):
    """Coerce one metadata value into something Chroma will accept, or None.

    Chroma stores scalar str/int/float/bool only. metadata.extra on a tabular
    unit is the RAW pandas row (see tabular_extractor), so it arrives full of
    numpy scalars, pandas Timestamps, and NaN — every one of which raises or
    silently corrupts on upsert. NaN is the common case: any blank cell in any
    spreadsheet produces one.
    """
    if value is None:
        return None
    if isinstance(value, bool):  # before int — bool is a subclass of int
        return value
    if isinstance(value, (int, float)):
        # NaN and infinities are floats but not storable, and NaN is what a
        # blank spreadsheet cell becomes.
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (datetime, date)):
        # pandas' NaT — a missing date — IS an instance of datetime, and its
        # isoformat() returns the literal string "NaT". Without this guard a
        # blank date cell is stored in Chroma as the text "NaT", which then
        # looks like real data to anyone reading the metadata.
        text = value.isoformat()
        return None if text.lower() in {"nat", "nan"} else text
    # numpy scalars (int64, float64, bool_) expose .item(); pandas NA-likes
    # do not survive the round trip and fall through to str().
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _scalarize(item())
        except (ValueError, TypeError):
            pass
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none", "<na>"}:
        return None
    return text


def unit_to_metadata(unit: KnowledgeUnit) -> dict:
    """Flatten a KnowledgeUnit into a Chroma-safe metadata dict.

    Downstream retrieval never reads specific keys out of `extra` (schema.py
    says so explicitly) — it is carried for human debugging and for future
    per-domain filtering. But it still has to be storable, hence _scalarize.
    """
    metadata = {
        "domain": unit.domain,
        "source_type": unit.source_type,
        "source_file": unit.metadata.source_file,
        "generated_at": unit.metadata.generated_at,
    }
    for key, raw in unit.metadata.extra.items():
        clean_key = str(key).strip()
        if not clean_key or clean_key in RESERVED_METADATA_KEYS:
            continue
        value = _scalarize(raw)
        if value is not None:
            metadata[clean_key] = value
    return metadata


def _load_existing(domain: str) -> tuple[list[str], list[str]]:
    """Return (ids, texts) already in the sparse index, or empty lists."""
    path = _bm25_path(domain)
    if not path.exists():
        return [], []
    with open(path, "rb") as f:
        data = pickle.load(f)
    return list(data.get("ids", [])), list(data.get("texts", []))


def build_index(units: list[KnowledgeUnit], domain: str) -> None:
    """Build/extend and persist both indexes for one domain.

    Collection name IS the domain, so `medical` and `financial` are physically
    separate indexes — a routing error can retrieve the wrong corpus, but it
    can never blend the two into one answer.

    Safe to call repeatedly with new batches: existing units are updated in
    place by ID, new ones are appended, nothing already indexed is lost.
    """
    if not units:
        print(f"No units to index for domain '{domain}' — nothing to do.")
        return

    mismatched = {u.domain for u in units} - {domain}
    if mismatched:
        raise ValueError(
            f"Refusing to index into collection '{domain}': "
            f"{len(units)} units carry domain(s) {sorted(mismatched)}. "
            "A unit's domain and its collection must agree, or the domain tag "
            "stops meaning anything at query time."
        )

    # Reuse the retrieval layer's cached instance rather than constructing a
    # second one. Loading all-MiniLM-L6-v2 takes ~20s, and build_index() is
    # called once per domain per ingest — so a fresh load here meant paying
    # that cost again for every batch, and holding two copies of the same
    # model in memory on a 512MB Render instance. Imported lazily so importing
    # this module still does not touch the model.
    from src.hybrid_retrieval import _get_embed_model

    embed_model = _get_embed_model()

    ids = [u.id for u in units]
    texts = [u.text for u in units]
    metadatas = [unit_to_metadata(u) for u in units]

    duplicates = len(ids) - len(set(ids))
    if duplicates:
        raise ValueError(
            f"{duplicates} duplicate ID(s) in this batch. IDs must be unique "
            "across the whole system — build them with schema.make_unit_id()."
        )

    # --- Dense index (Chroma merges by ID itself, via upsert) ---
    chroma_client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = chroma_client.get_or_create_collection(name=domain)
    embeddings = embed_model.encode(texts, show_progress_bar=True).tolist()
    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)

    # --- Sparse index (merge by hand: rank-bm25 has no incremental API) ---
    merged: dict[str, str] = dict(zip(*_load_existing(domain)))
    previously_held = len(merged)
    merged.update(zip(ids, texts))  # this batch wins on a duplicate ID

    all_ids = list(merged.keys())
    all_texts = list(merged.values())

    # Persist the CORPUS, not the fitted BM25 object. A pickled BM25Okapi
    # couples this artifact to the installed rank-bm25 and Python versions, so
    # it can fail to unpickle on a deployment host whose versions differ.
    # Refitting on load is O(n) over a few hundred short documents.
    path = _bm25_path(domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump({"ids": all_ids, "texts": all_texts}, f)

    added = len(all_ids) - previously_held
    print(f"Indexed {len(units)} units into domain '{domain}'")
    print(f"  Dense index:  Chroma collection '{domain}' at {CHROMA_DIR}")
    print(f"  Sparse index: {path}")
    print(
        f"  Corpus now {len(all_ids)} documents "
        f"({previously_held} already held, {added} new, "
        f"{len(units) - added} updated in place)"
    )


def load_bm25(domain: str) -> tuple[BM25Okapi, list[str], list[str]]:
    """Load the sparse corpus and fit BM25 over it. Used by hybrid_retrieval."""
    ids, texts = _load_existing(domain)
    if not ids:
        raise FileNotFoundError(
            f"No sparse index for domain '{domain}' at {_bm25_path(domain)}. "
            f"Run `python -m src.main index --domain {domain}` first."
        )
    return BM25Okapi([tokenize_for_bm25(t) for t in texts]), ids, texts
