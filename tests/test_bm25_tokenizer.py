"""BM25 tokenization — the Unicode bug that disabled sparse retrieval.

BM25 is in this system for one reason: exact matches that dense embeddings
miss — ticker symbols, sample IDs, drug names.

The narrative generator is an LLM, and it writes "TC‑014" using a NON-BREAKING
HYPHEN. A user types "TC-014" with an ordinary one. Those tokenize differently,
so the query scored 0.0000 against EVERY document in the corpus and BM25
contributed nothing at all to the fusion. It failed silently, because RRF still
returned a ranked list that looked like ordinary ranking.

Worse, the obvious test passes by accident: with every score at 0.0, sorted()
returns insertion order, and the target document happened to be index 0. So
`assert target in results` was GREEN while retrieval was completely broken.
That is why the tests below assert on SCORES, not on membership.
"""
import pytest

from src.build_index import normalize_for_bm25, tokenize_for_bm25

NB_HYPHEN = "‑"
EM_DASH = "—"
CURLY_APOS = "’"
NARROW_NBSP = " "


class TestTypographyFolding:
    def test_non_breaking_hyphen_becomes_ascii(self):
        """THE regression."""
        assert tokenize_for_bm25(f"TC{NB_HYPHEN}014") == tokenize_for_bm25("TC-014")

    @pytest.mark.parametrize("dash", ["‐", "‑", "‒", "–", "—", "―"])
    def test_every_dash_variant_folds_to_ascii_hyphen(self, dash):
        assert tokenize_for_bm25(f"AB{dash}123") == ["ab-123"]

    def test_curly_apostrophe_folds(self):
        assert tokenize_for_bm25(f"don{CURLY_APOS}t") == tokenize_for_bm25("don't")

    def test_curly_quotes_are_stripped_like_ascii_quotes(self):
        assert tokenize_for_bm25("“robust”") == tokenize_for_bm25('"robust"') == ["robust"]

    def test_exotic_whitespace_splits_tokens(self):
        assert tokenize_for_bm25(f"alpha{NARROW_NBSP}beta") == ["alpha", "beta"]

    def test_nfkc_normalization_is_applied(self):
        """Fullwidth characters fold to ASCII."""
        assert tokenize_for_bm25("ＴＣ-014") == ["tc-014"]


class TestTokenization:
    def test_case_is_folded(self):
        assert tokenize_for_bm25("JGCHEM") == tokenize_for_bm25("jgchem") == ["jgchem"]

    def test_trailing_punctuation_is_stripped(self):
        assert tokenize_for_bm25("hyperglycemia.") == ["hyperglycemia"]
        assert tokenize_for_bm25("(n=40),") == ["n=40"]

    def test_internal_structure_is_preserved(self):
        """Splitting on hyphens would destroy the identifiers BM25 exists for."""
        assert tokenize_for_bm25("TC-014") == ["tc-014"]

    def test_empty_and_whitespace_only_yield_nothing(self):
        assert tokenize_for_bm25("") == []
        assert tokenize_for_bm25("   \n\t ") == []

    def test_punctuation_only_token_is_dropped(self):
        assert tokenize_for_bm25("word --- word") == ["word", "word"]

    def test_normalize_is_idempotent(self):
        once = normalize_for_bm25(f"TC{NB_HYPHEN}014 {EM_DASH} “ok”")
        assert normalize_for_bm25(once) == once


class TestScoringNotMembership:
    """The tests that would have caught the bug. Membership assertions do not."""

    @pytest.fixture
    def corpus(self):
        from rank_bm25 import BM25Okapi

        docs = [
            f"Sample TC{NB_HYPHEN}014 showed an activation score of 0.87.",
            "Sample TC-015 showed no significant activation.",
            "Unrelated document about quarterly revenue growth.",
        ]
        return BM25Okapi([tokenize_for_bm25(d) for d in docs]), docs

    def test_user_typed_hyphen_scores_a_real_match(self, corpus):
        """Pre-fix this was 0.0000 across the whole corpus."""
        bm25, _ = corpus
        scores = bm25.get_scores(tokenize_for_bm25("TC-014"))
        assert max(scores) > 0, "query matched nothing — sparse retrieval is dead"
        assert scores.argmax() == 0

    def test_both_hyphen_forms_score_identically(self, corpus):
        bm25, _ = corpus
        assert list(bm25.get_scores(tokenize_for_bm25("TC-014"))) == list(
            bm25.get_scores(tokenize_for_bm25(f"TC{NB_HYPHEN}014"))
        )

    def test_a_genuinely_absent_term_still_scores_zero(self, corpus):
        """Normalization must not turn everything into a match."""
        bm25, _ = corpus
        assert max(bm25.get_scores(tokenize_for_bm25("ibuprofen"))) == 0

    def test_index_and_query_tokenizers_are_the_same_function(self):
        """If indexing and querying ever diverge, sparse silently returns
        nothing and hybrid degrades to dense-only without erroring."""
        from src import hybrid_retrieval

        assert hybrid_retrieval.tokenize_for_bm25 is tokenize_for_bm25
