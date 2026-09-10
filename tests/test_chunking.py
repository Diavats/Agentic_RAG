"""Chunking correctness — the two bugs that would have poisoned the index.

BUG A (silent truncation). Chunks were 500 tokens against an embedding model
whose max_seq_length is 256. sentence-transformers truncates at encode time
with no warning, so the back half of every chunk contributed NOTHING to its
dense vector while still being stored and still being fed to synthesis. BM25
(which indexes the full text) masked the resulting recall hole.

BUG B (mangled citations). Chunks were rebuilt with tokenizer.decode(). The
MiniLM tokenizer has do_lower_case=true and splits punctuation onto its own
tokens, so "Dr. Smith reported 5.2%" came back as "dr. smith reported 5. 2 %".
That string is what lands in KnowledgeUnit.text -> Chroma -> the synthesis
prompt -> the citation block a viva panel reads.

These tests load the real embedding model, because both bugs are properties of
that specific tokenizer. Stubbing it would test nothing.
"""
import docx
import pytest

from src.extractors import text_extractor

pytestmark = pytest.mark.model


@pytest.fixture(scope="module")
def messy_docx(tmp_path_factory):
    """A document containing exactly what breaks naive chunkers."""
    path = tmp_path_factory.mktemp("docs") / "messy.docx"
    document = docx.Document()
    document.add_heading("Clinical Protocol", 0)
    document.add_heading("1. Screening", level=1)
    document.add_paragraph(
        "Dr. Smith reported 5.2% uptake (n=40) across the ACME-2 cohort. "
        "Subjects with HbA1c above 7.5% were flagged for review by the PI."
    )
    document.add_paragraph(
        "Sample TC-014 showed hyperglycemia; the CONSORT diagram is in Appendix B."
    )
    document.add_heading("2. Exclusion", level=1)
    for i in range(60):
        document.add_paragraph(
            f"Exclusion clause {i}: subjects presenting with condition {i} are "
            f"ineligible unless the treating physician provides written clearance "
            f"referencing protocol section {i}.{i}."
        )
    document.save(path)
    return str(path)


class TestChunkSizeDerivation:
    def test_chunk_size_comes_from_the_model_not_a_constant(self, embed_model):
        """Regression for BUG A. 500 > 256 was the bug; the fix is not
        'hardcode 224' but 'ask the model'."""
        assert text_extractor.chunk_size_tokens() < embed_model.max_seq_length

    def test_chunk_size_leaves_room_for_special_tokens(self, embed_model):
        """The encoder prepends [CLS] and appends [SEP]."""
        assert text_extractor.chunk_size_tokens() <= embed_model.max_seq_length - 2

    def test_every_chunk_fits_the_encoder_without_truncation(self, messy_docx, embed_model):
        """The property that actually matters: nothing gets silently dropped."""
        tokenizer = embed_model.tokenizer
        limit = embed_model.max_seq_length - 2
        units = text_extractor.extract_text(messy_docx)
        assert units, "fixture produced no chunks"
        for unit in units:
            n = len(tokenizer.encode(unit.text, add_special_tokens=False))
            assert n <= limit, f"{unit.id} is {n} tokens, encoder truncates at {limit}"


class TestTextFidelity:
    def test_chunk_text_is_verbatim_from_the_document(self, messy_docx):
        """Regression for BUG B: every chunk must be a literal substring of
        the source, not a decode() reconstruction of it."""
        source = "\n\n".join(
            p.text.strip()
            for p in docx.Document(messy_docx).paragraphs
            if p.text.strip() and p.style.name not in text_extractor.HEADING_STYLES
        )
        for unit in text_extractor.extract_text(messy_docx):
            assert unit.text in source, f"{unit.id} is not verbatim source text"

    def test_capitalisation_survives(self, messy_docx):
        """decode() lowercases everything. Proper nouns and drug names matter."""
        combined = " ".join(u.text for u in text_extractor.extract_text(messy_docx))
        assert "Dr. Smith" in combined
        assert "HbA1c" in combined

    def test_punctuation_spacing_survives(self, messy_docx):
        """decode() renders these as '5. 2 %' and '( n = 40 )'."""
        combined = " ".join(u.text for u in text_extractor.extract_text(messy_docx))
        assert "5.2%" in combined
        assert "(n=40)" in combined
        assert "5. 2 %" not in combined

    def test_paragraphs_are_separated(self, messy_docx):
        """Paragraphs were token-concatenated with no separator, so the last
        word of one ran into the first word of the next."""
        combined = " ".join(u.text for u in text_extractor.extract_text(messy_docx))
        assert "reviewSample" not in combined


class TestChunkStructure:
    def test_overlap_exists_between_consecutive_chunks(self, messy_docx):
        units = text_extractor.extract_text(messy_docx)
        assert len(units) > 1, "fixture should be long enough to split"

    def test_units_carry_section_and_title_metadata(self, messy_docx):
        for unit in text_extractor.extract_text(messy_docx):
            assert unit.metadata.extra["section"]
            assert unit.metadata.extra["document_title"]

    def test_units_are_tagged_medical_textual(self, messy_docx):
        for unit in text_extractor.extract_text(messy_docx):
            assert (unit.domain, unit.source_type) == ("medical", "textual")

    def test_ids_unique_within_a_document(self, messy_docx):
        ids = [u.id for u in text_extractor.extract_text(messy_docx)]
        assert len(ids) == len(set(ids))

    def test_empty_document_yields_no_chunks(self, tmp_path):
        path = tmp_path / "empty.docx"
        docx.Document().save(path)
        assert text_extractor.extract_text(str(path)) == []

    def test_headings_are_not_emitted_as_body_chunks(self, messy_docx):
        """Headings become section labels, not retrievable content."""
        units = text_extractor.extract_text(messy_docx)
        assert not any(u.text.strip() == "1. Screening" for u in units)
