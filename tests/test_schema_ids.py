"""KnowledgeUnit ID contract.

Regression suite for a silent data-loss bug: both extractors used to number
units from 0 per file, so the tcell CSV and the human-subject CSV both emitted
`medical_tabular_0000`. Chroma upsert overwrites by ID, so ingesting the second
file SILENTLY DELETED the first file's units — in exactly the incremental
arrival scenario PRD section 10 says is normal.

Pydantic cannot type-check cross-file uniqueness, so it has to be tested.
"""
import pytest

from src.schema import KnowledgeUnit, KnowledgeUnitMetadata, make_unit_id, source_slug


class TestUniqueness:
    def test_same_index_different_files_do_not_collide(self):
        """THE regression. Two medical CSVs, both row 0."""
        a = make_unit_id("medical", "tabular", "tcell_antigen.csv", 0)
        b = make_unit_id("medical", "tabular", "human_filtered.csv", 0)
        assert a != b

    def test_same_stem_different_extension_do_not_collide(self):
        """data.csv and data.docx are different sources."""
        assert make_unit_id("medical", "tabular", "data.csv", 0) != make_unit_id(
            "medical", "textual", "data.docx", 0
        )

    def test_long_filenames_sharing_a_prefix_do_not_collide(self):
        """The slug is truncated for readability; the hash covers the rest."""
        long_a = "medical_experiment_batch_from_lab_" + "a" * 40 + ".csv"
        long_b = "medical_experiment_batch_from_lab_" + "b" * 40 + ".csv"
        assert make_unit_id("medical", "tabular", long_a, 0) != make_unit_id(
            "medical", "tabular", long_b, 0
        )

    def test_ids_unique_across_a_realistic_multi_file_ingest(self):
        ids = [
            make_unit_id(domain, stype, fname, i)
            for domain, stype, fname in [
                ("medical", "tabular", "tcell.csv"),
                ("medical", "tabular", "human.csv"),
                ("medical", "textual", "guideline.docx"),
                ("financial", "tabular", "stocks.csv"),
            ]
            for i in range(20)
        ]
        assert len(ids) == len(set(ids)) == 80


class TestStability:
    def test_id_is_deterministic(self):
        """Re-ingesting a file must UPDATE its units, not duplicate them —
        which requires the same inputs to yield the same ID every time."""
        args = ("financial", "tabular", "sample_stocks.csv", 7)
        assert make_unit_id(*args) == make_unit_id(*args)

    def test_id_does_not_depend_on_content_or_time(self):
        """Only (domain, source_type, filename, position) may affect the ID."""
        first = make_unit_id("medical", "textual", "g.docx", 3)
        import time

        time.sleep(0.01)
        assert make_unit_id("medical", "textual", "g.docx", 3) == first


class TestReadability:
    def test_id_contains_the_source_stem(self):
        """IDs appear in citations and in eval gold_chunk_ids. A bare hash
        would be unusable when hand-labelling."""
        assert "sample_stocks" in make_unit_id("financial", "tabular", "sample_stocks.csv", 0)

    def test_id_carries_domain_and_source_type(self):
        unit_id = make_unit_id("medical", "textual", "g.docx", 12)
        assert unit_id.startswith("medical_textual_")
        assert unit_id.endswith("_0012")

    @pytest.mark.parametrize(
        "filename, expected",
        [
            ("Sample Stocks (2026).csv", "sample_stocks_2026"),
            ("../../etc/passwd.csv", "passwd"),
            ("....csv", "unknown"),
            ("données_médicales.csv", "donn_es_m_dicales"),
        ],
    )
    def test_slug_is_filesystem_and_id_safe(self, filename, expected):
        assert source_slug(filename) == expected


class TestSchemaContract:
    def test_domain_is_constrained(self):
        with pytest.raises(Exception):
            KnowledgeUnit(
                id="x", domain="legal", source_type="tabular", text="t",
                metadata=KnowledgeUnitMetadata(source_file="f.csv"),
            )

    def test_source_type_is_constrained(self):
        with pytest.raises(Exception):
            KnowledgeUnit(
                id="x", domain="medical", source_type="pdf", text="t",
                metadata=KnowledgeUnitMetadata(source_file="f.pdf"),
            )

    def test_domain_and_source_type_vary_independently(self):
        """The architectural claim: format and domain are separate axes, so
        medical+tabular and medical+textual must both be valid."""
        for stype in ("tabular", "textual"):
            unit = KnowledgeUnit(
                id=make_unit_id("medical", stype, "f", 0), domain="medical",
                source_type=stype, text="t",
                metadata=KnowledgeUnitMetadata(source_file="f"),
            )
            assert unit.source_type == stype

    def test_extra_survives_round_trip(self):
        unit = KnowledgeUnit(
            id="x", domain="financial", source_type="tabular", text="t",
            metadata=KnowledgeUnitMetadata(source_file="f.csv", extra={"ticker": "JGCHEM"}),
        )
        assert KnowledgeUnit.model_validate_json(unit.model_dump_json()).metadata.extra == {
            "ticker": "JGCHEM"
        }
