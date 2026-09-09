"""
Text Extractor Agent — Phase 3.

Ingests medical DOCX documents, splits them into retrievable chunks, and
wraps each chunk as a KnowledgeUnit with domain="medical" and
source_type="textual" — the same shape src/extractors/tabular_extractor.py
produces, so nothing downstream (indexing, retrieval, the agent) needs to
know or care whether a unit came from a spreadsheet or a document.

See docs/AGENTS.md, Agent 5, for the full spec this implements.

--- Chunking: two things worth defending in a viva ---

1. Chunk size is DERIVED from the embedding model, not copied from a blog
   post. all-MiniLM-L6-v2 has max_seq_length=256; sentence-transformers
   truncates anything longer at encode time SILENTLY, with no warning. The
   original 500-token setting meant the back half of every chunk contributed
   nothing to its dense vector, while the full text was still stored and
   still fed to synthesis — a recall hole that BM25 (which indexes the full
   text) masked in hybrid results. Reading the limit off the model means the
   chunker stays correct if the embedding model is ever swapped, which
   PRD section 8 lists as Flexible.

2. Chunk boundaries are measured in TOKENS but sliced in CHARACTERS. The
   obvious implementation — encode, window, tokenizer.decode() — silently
   destroys the text: MiniLM's tokenizer has do_lower_case=true and splits
   punctuation onto its own tokens, so a phrase like
       Dr. Smith reported 5.2% uptake (n=40)
   decodes back as
       dr. smith reported 5. 2 % uptake ( n = 40 )
   That string is what lands in KnowledgeUnit.text -> Chroma documents ->
   the synthesis prompt -> the citation block in the UI. Using the fast
   tokenizer's offset_mapping to slice the ORIGINAL string keeps boundaries
   token-exact and content byte-identical to the source document.
"""
from pathlib import Path

import docx

from src.config import EMBEDDING_MODEL
from src.schema import KnowledgeUnit, KnowledgeUnitMetadata, make_unit_id

# Tokens reserved so a chunk still fits after the encoder adds [CLS]/[SEP]
# and after any tokenizer-version drift. 2 would be strictly enough; 32 is
# cheap insurance against an off-by-a-few silently truncating again.
SPECIAL_TOKEN_HEADROOM = 32
OVERLAP_TOKENS = 40

HEADING_STYLES = {"Title", "Heading 1", "Heading 2", "Heading 3"}

_model = None


def _get_model():
    """Lazy-load the embedding model (not at import time, so importing this
    file never triggers a download — only calling extract_text() does).

    We need the whole SentenceTransformer, not just its tokenizer: the
    tokenizer reports model_max_length=512 (the BERT architecture limit),
    but sentence-transformers actually truncates at max_seq_length=256,
    which lives on the SentenceTransformer object. Reading the tokenizer's
    limit is exactly the mistake that produced the original 500-token bug.
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def chunk_size_tokens() -> int:
    """Content-token budget per chunk, derived from the embedding model."""
    return max(_get_model().max_seq_length - SPECIAL_TOKEN_HEADROOM, 64)


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
    chunk_size: int | None = None,
    overlap: int = OVERLAP_TOKENS,
) -> list[tuple[str, str]]:
    """Window over TOKENS, slice the ORIGINAL text by CHARACTERS.

    Returns [(chunk_text, section_label), ...] where every chunk_text is a
    verbatim substring of the source document — original casing, original
    punctuation, original spacing — while its length in tokens is still
    exactly what the embedding model will consume at index time.
    """
    if chunk_size is None:
        chunk_size = chunk_size_tokens()

    tokenizer = _get_model().tokenizer
    if not getattr(tokenizer, "is_fast", False):
        raise RuntimeError(
            "Chunking needs a fast tokenizer for offset_mapping (character "
            "offsets). sentence-transformers normally loads BertTokenizerFast; "
            f"got {type(tokenizer).__name__}. Without offsets we would have to "
            "fall back to tokenizer.decode(), which lowercases the text and "
            "mangles punctuation in every citation."
        )

    # Rebuild the document as one string, remembering where each paragraph
    # starts. Joining with a blank line also fixes a quieter bug in the
    # previous implementation: paragraphs were token-concatenated with no
    # separator, so the last word of one ran into the first word of the next.
    separator = "\n\n"
    source_parts: list[str] = []
    paragraph_starts: list[int] = []
    cursor = 0
    for text, _section in tagged_paragraphs:
        paragraph_starts.append(cursor)
        source_parts.append(text)
        cursor += len(text) + len(separator)
    source = separator.join(source_parts)

    # (char_start, char_end, section) per token, across the whole document.
    # Tokenizing per paragraph (rather than the joined string) keeps each
    # call under the tokenizer's length-warning threshold and lets us attach
    # the section label without a second lookup.
    tokens: list[tuple[int, int, str]] = []
    for (text, section), para_start in zip(tagged_paragraphs, paragraph_starts):
        encoded = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
        for start_char, end_char in encoded["offset_mapping"]:
            if end_char <= start_char:
                continue  # degenerate/zero-width token, carries no text
            tokens.append((para_start + start_char, para_start + end_char, section))

    if not tokens:
        return []

    chunks: list[tuple[str, str]] = []
    start = 0
    n = len(tokens)
    step = max(chunk_size - overlap, 1)  # guard against overlap >= chunk_size

    while start < n:
        end = min(start + chunk_size, n)
        window = tokens[start:end]
        chunk_text = source[window[0][0]:window[-1][1]]
        chunks.append((chunk_text, window[0][2]))
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
        One KnowledgeUnit per chunk, source_type="textual". IDs are unique
        across source files (see schema.make_unit_id) — medical DOCX
        documents arrive in pieces, and a per-file counter would make the
        second document silently overwrite the first on Chroma upsert.
    """
    document_title, tagged_paragraphs = _read_docx(file_path)
    source_file = Path(file_path).name
    chunks = _chunk_by_tokens(tagged_paragraphs)

    units: list[KnowledgeUnit] = []
    for i, (chunk_text, section_label) in enumerate(chunks):
        unit = KnowledgeUnit(
            id=make_unit_id("medical", "textual", source_file, i),
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
    print(
        f"=== chunk size derived from {EMBEDDING_MODEL}: "
        f"{chunk_size_tokens()} content tokens "
        f"(max_seq_length={_get_model().max_seq_length}) ===\n"
    )

    print("=== medical: data/medical_guideline_placeholder.docx ===")
    units = extract_text("data/medical_guideline_placeholder.docx")
    print(f"\n{len(units)} chunks extracted\n")
    print(units[0].model_dump_json(indent=2))
    if len(units) > 1:
        print("---")
        print(units[-1].model_dump_json(indent=2))
