"""Indexing: Chroma metadata safety, incremental ingestion, domain isolation.

The headline regression here is incremental ingestion (RULES section 3,
non-negotiable 10). Chroma survives re-ingestion via upsert; BM25 did not.
rank-bm25 has no incremental API, and the old code rebuilt the index from only
the batch passed in and overwrote the pickle — leaving the dense index holding
every unit and the sparse index holding only the newest batch. Hybrid search
kept returning plausible results, so the corpus loss was invisible.

Medical data arrives in pieces, so this is the normal path, not an edge case.
"""
import math
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.build_index import (
    RESERVED_METADATA_KEYS,
    _scalarize,
    build_index,
    load_bm25,
    unit_to_metadata,
)

pytestmark = pytest.mark.model


class TestScalarize:
    """Chroma stores scalar str/int/float/bool only. metadata.extra is the RAW
    pandas row, so it arrives full of things that raise on upsert."""

    def test_nan_becomes_none(self):
        """Any blank cell in any spreadsheet produces one of these."""
        assert _scalarize(float("nan")) is None
        assert _scalarize(np.nan) is None

    def test_infinities_become_none(self):
        assert _scalarize(float("inf")) is None
        assert _scalarize(float("-inf")) is None

    def test_pandas_na_becomes_none(self):
        assert _scalarize(pd.NA) is None
        assert _scalarize(pd.NaT) is None

    def test_numpy_scalars_become_python_scalars(self):
        assert _scalarize(np.int64(42)) == 42
        assert isinstance(_scalarize(np.int64(42)), int)
        assert _scalarize(np.float64(1.5)) == 1.5

    def test_numpy_bool_stays_bool_not_int(self):
        assert _scalarize(np.bool_(True)) is True

    def test_bool_is_not_coerced_to_int(self):
        """bool is a subclass of int, so order of isinstance checks matters."""
        assert _scalarize(True) is True

    def test_timestamps_become_iso_strings(self):
        assert _scalarize(pd.Timestamp("2026-03-01")).startswith("2026-03-01")
        assert _scalarize(datetime(2026, 3, 1)).startswith("2026-03-01")

    def test_blank_strings_become_none(self):
        assert _scalarize("") is None
        assert _scalarize("   ") is None

    def test_ordinary_values_pass_through(self):
        assert _scalarize("JGCHEM") == "JGCHEM"
        assert _scalarize(0.1517) == 0.1517

    def test_every_output_is_chroma_safe(self):
        """The property that matters, over everything a spreadsheet can hold."""
        for raw in [np.nan, pd.NA, pd.NaT, np.int64(3), np.float64(2.5), np.bool_(False),
                    pd.Timestamp("2026-01-01"), "", "  x  ", True, 7, 1.5, None]:
            out = _scalarize(raw)
            assert out is None or isinstance(out, (str, int, float, bool))


class TestMetadataFlattening:
    def test_core_fields_are_written(self, make_unit):
        meta = unit_to_metadata(make_unit("t", extra={"ticker": "JGCHEM"}))
        assert meta["domain"] == "financial"
        assert meta["source_type"] == "tabular"
        assert meta["source_file"] == "test.csv"
        assert meta["ticker"] == "JGCHEM"

    def test_extra_cannot_override_reserved_keys(self, make_unit):
        """A CSV with a column literally named 'domain' must not be able to
        relabel which collection a unit claims to belong to."""
        hostile = {key: "HIJACKED" for key in RESERVED_METADATA_KEYS}
        meta = unit_to_metadata(make_unit("t", domain="financial", extra=hostile))
        assert meta["domain"] == "financial"
        assert meta["source_type"] == "tabular"
        assert "HIJACKED" not in meta.values()

    def test_nan_valued_columns_are_dropped_not_stored(self, make_unit):
        meta = unit_to_metadata(make_unit("t", extra={"blank": np.nan, "real": 1}))
        assert "blank" not in meta
        assert meta["real"] == 1

    def test_a_full_pandas_row_survives(self, make_unit):
        """The realistic case: extract_tabular puts the whole row in extra."""
        row = pd.DataFrame(
            [{"Sym": "JGCHEM", "Growth": 0.15, "Q": pd.Timestamp("2026-03-01"), "Note": None}]
        ).to_dict("records")[0]
        meta = unit_to_metadata(make_unit("t", extra=row))
        assert all(v is None or isinstance(v, (str, int, float, bool)) for v in meta.values())
        assert not any(isinstance(v, float) and math.isnan(v) for v in meta.values())


class TestGuards:
    def test_rejects_units_whose_domain_disagrees_with_the_collection(
        self, isolated_store, make_unit
    ):
        with pytest.raises(ValueError, match="domain"):
            build_index([make_unit("t", domain="medical")], "financial")

    def test_rejects_duplicate_ids_within_a_batch(self, isolated_store, make_unit):
        unit = make_unit("t")
        with pytest.raises(ValueError, match="[Dd]uplicate"):
            build_index([unit, unit], "financial")

    def test_empty_batch_is_a_no_op_not_a_crash(self, isolated_store):
        build_index([], "financial")

    def test_missing_index_raises_an_actionable_error(self, isolated_store):
        with pytest.raises(FileNotFoundError, match="index"):
            load_bm25("financial")


class TestIncrementalIngestion:
    """THE regression: data arrives in pieces and must accumulate."""

    def test_second_batch_does_not_destroy_the_first(self, isolated_store, make_unit):
        batch_a = [make_unit(f"alpha document {i}", source_file="a.csv", index=i)
                   for i in range(3)]
        batch_b = [make_unit(f"beta document {i}", source_file="b.csv", index=i)
                   for i in range(2)]

        build_index(batch_a, "financial")
        build_index(batch_b, "financial")

        _, ids, _ = load_bm25("financial")
        assert len(ids) == 5, "sparse index lost the first batch"
        assert {u.id for u in batch_a} <= set(ids)
        assert {u.id for u in batch_b} <= set(ids)

    def test_dense_and_sparse_hold_the_same_corpus(self, isolated_store, make_unit):
        """Two artifacts per domain and nothing checks they agree — so the
        test has to."""
        import chromadb

        build_index([make_unit("a", source_file="a.csv", index=i) for i in range(3)], "financial")
        build_index([make_unit("b", source_file="b.csv", index=i) for i in range(2)], "financial")

        _, sparse_ids, _ = load_bm25("financial")
        dense = chromadb.PersistentClient(path=str(isolated_store)).get_collection("financial")
        assert set(dense.get()["ids"]) == set(sparse_ids)

    def test_reingesting_the_same_file_updates_in_place(self, isolated_store, make_unit):
        build_index([make_unit("original text", source_file="a.csv", index=0)], "financial")
        build_index([make_unit("revised text", source_file="a.csv", index=0)], "financial")

        _, ids, texts = load_bm25("financial")
        assert len(ids) == 1, "re-ingestion duplicated instead of updating"
        assert texts[0] == "revised text"

    def test_a_term_from_the_first_batch_is_still_findable(self, isolated_store, make_unit):
        """The user-visible symptom of the original bug.

        The corpus is deliberately not tiny. BM25Okapi computes
        idf = log(N - freq + 0.5) - log(freq + 0.5), which is EXACTLY 0 when a
        term appears in one of two documents — so a 2-document version of this
        test fails while the code under test is perfectly correct. Measured:
        a term in 1 document scores 0.00 at N=2, 0.51 at N=3, 1.95 at N=11.
        """
        build_index([make_unit("unique zebra content", source_file="a.csv", index=0)], "financial")
        build_index(
            [make_unit(f"ordinary filler {i}", source_file="b.csv", index=i) for i in range(7)],
            "financial",
        )

        from src.build_index import tokenize_for_bm25

        bm25, ids, _ = load_bm25("financial")
        scores = bm25.get_scores(tokenize_for_bm25("zebra"))
        assert len(ids) == 8, "sparse index lost a batch"
        assert max(scores) > 0, "first batch became unsearchable"
        assert scores.argmax() == ids.index(
            make_unit("x", source_file="a.csv", index=0).id
        ), "the zebra document is not the top hit"


class TestDomainIsolation:
    def test_collections_are_independent(self, isolated_store, make_unit):
        build_index([make_unit("stock growth", domain="financial", index=0)], "financial")
        build_index(
            [make_unit("antigen panel", domain="medical", source_file="m.csv", index=0)],
            "medical",
        )
        _, fin_ids, _ = load_bm25("financial")
        _, med_ids, _ = load_bm25("medical")
        assert set(fin_ids).isdisjoint(med_ids)
        assert len(fin_ids) == len(med_ids) == 1

    def test_indexing_one_domain_leaves_the_other_untouched(self, isolated_store, make_unit):
        build_index([make_unit("m", domain="medical", source_file="m.csv", index=0)], "medical")
        before = load_bm25("medical")[1]
        build_index([make_unit("f", domain="financial", index=0)], "financial")
        assert load_bm25("medical")[1] == before
