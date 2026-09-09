"""
Text Extractor Agent — Phase 3.

Ingests medical DOCX documents, splits them into retrievable chunks, and
wraps each chunk as a KnowledgeUnit with domain="medical" and
source_type="textual" — the same shape src/extractors/tabular_extractor.py
produces, so nothing downstream (indexing, retrieval, the agent) needs to
know or care whether a unit came from a spreadsheet or a document.

See docs/AGENTS.md, Agent 5, for the full spec this implements.

Chunking note: chunk size is measured with the SAME tokenizer the
embedding model (config.EMBEDDING_MODEL, all-MiniLM-L6-v2) uses at index
time — not approximated from word count. This needed no new dependency:
sentence-transformers (already in requirements.txt) ships the tokenizer
via SentenceTransformer(...).tokenizer. The tokenizer downloads on first
use, same as it will for Phase 4 indexing.
"""
from pathlib import Path

import docx

from src.config import EMBEDDING_MODEL
from src.schema import KnowledgeUnit, KnowledgeUnitMetadata

CHUNK_SIZE_TOKENS = 500
OVERLAP_TOKENS = 50

HEADING_STYLES = {"Title", "Heading 1", "Heading 2", "Heading 3"}

_tokenizer = None


def _get_tokenizer():
    """Lazy-load the real embedding-model tokenizer (not imported at
    module load time, so importing this file never triggers a download —
    only actually calling extract_text() does)."""
    global _tokenizer
    if _tokenizer is None:
        from sentence_transformers import SentenceTransformer

        _tokenizer = SentenceTransformer(EMBEDDING_MODEL).tokenizer
    return _tokenizer


def _read_docx(file_path: str) -> tuple[str, list[tuple[str, str]]]:
    """Read a .docx file into (document_title, [(paragraph_text, section_label), ...]).

    section_label is the text of the most recent heading-style paragraph
    seen before each paragraph — best-effort section tagging, not exact,
    since a chunk can still straddle a heading boundary.
    """
    document = docx.Document(file_path)

    document_title = Path(file_path).stem
    current_section = document_title
    tagged_paragraphs: list[tuple[str, str]] = []
    seen_title = False

    for para in document.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        style_name = para.style.name if para.style else ""
        if style_name in HEADING_STYLES:
            if style_name == "Title" and not seen_title:
                document_title = text
                seen_title = True
            current_section = text
            continue  # heading text itself isn't chunked as body content

        tagged_paragraphs.append((text, current_section))

    return document_title, tagged_paragraphs


def _chunk_by_tokens(
    tagged_paragraphs: list[tuple[str, str]],
    chunk_size: int = CHUNK_SIZE_TOKENS,
    overlap: int = OVERLAP_TOKENS,
) -> list[tuple[str, str]]:
    """Tokenize each paragraph with the real embedding-model tokenizer,
    flatten into one (token_id, section_label) stream, then slide a
    window over TOKENS (not words) -> [(chunk_text, section_label), ...].

    Chunk text is reconstructed with tokenizer.decode(), so what gets
    measured against chunk_size is exactly what the embedding model will
    consume at index time — not a word-count proxy for it.
    """
    tokenizer = _get_tokenizer()

    tagged_tokens: list[tuple[int, str]] = []
    for text, section in tagged_paragraphs:
        token_ids = tokenizer.encode(text, add_special_tokens=False)
        tagged_tokens.extend((tid, section) for tid in token_ids)

    if not tagged_tokens:
        return []

    chunks: list[tuple[str, str]] = []
    start = 0
    n = len(tagged_tokens)
    step = max(chunk_size - overlap, 1)  # guard against overlap >= chunk_size

    while start < n:
        end = min(start + chunk_size, n)
        window = tagged_tokens[start:end]
        window_ids = [tid for tid, _ in window]
        chunk_text = tokenizer.decode(window_ids, skip_special_tokens=True)
        section_label = window[0][1]
        chunks.append((chunk_text, section_label))
        if end == n:
            break
        start += step

    return chunks


def extract_text(file_path: str) -> list[KnowledgeUnit]:
    """Turn one .docx file into a list of KnowledgeUnits, one per chunk.

    Args:
        file_path: path to a .docx file. domain is always "medical" —
            hardcoded deliberately, since this extractor is semantically
            tied to the medical domain (unlike the tabular extractor,
            which is cross-domain and requires an explicit domain arg).

    Returns:
        One KnowledgeUnit per chunk, source_type="textual", id following
        "medical_textual_{index:04d}".
    """
    document_title, tagged_paragraphs = _read_docx(file_path)
    source_file = Path(file_path).name
    chunks = _chunk_by_tokens(tagged_paragraphs)

    units: list[KnowledgeUnit] = []
    for i, (chunk_text, section_label) in enumerate(chunks):
        unit = KnowledgeUnit(
            id=f"medical_textual_{i:04d}",
            domain="medical",
            source_type="textual",
            text=chunk_text,
            metadata=KnowledgeUnitMetadata(
                source_file=source_file,
                extra={"section": section_label, "document_title": document_title},
            ),
        )
        units.append(unit)
        print(f"  extracted {unit.id}  (section: {section_label})")

    return units


if __name__ == "__main__":
    print("=== medical: data/medical_guideline_placeholder.docx ===")
    units = extract_text("data/medical_guideline_placeholder.docx")
    print(f"\n{len(units)} chunks extracted\n")
    print(units[0].model_dump_json(indent=2))
    if len(units) > 1:
        print("---")
        print(units[-1].model_dump_json(indent=2))