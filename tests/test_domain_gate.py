"""The upload gate: finance and medical files get in, everything else is refused.

Runs against the REAL committed units (rebuilt into a temp index), because the
0.20 threshold was calibrated against them (ADR-001). Zero API calls: the gate
only embeds raw text, it never asks an LLM.
"""
import docx
import pytest

from src.api import sessions as sandbox
from src.build_index import build_index
from src.extractors.text_extractor import extract_text
from src.unit_store import load_units

pytestmark = pytest.mark.model


@pytest.fixture
def real_corpora(isolated_store):
    """Index the deployed corpora into the test's own temp folder."""
    for domain in ("medical", "financial"):
        build_index(load_units(domain), domain)


def write_csv(tmp_path, name, header, rows):
    path = tmp_path / name
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def write_docx(tmp_path, name, paragraphs):
    path = tmp_path / name
    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    document.save(path)
    return path


def test_a_finance_sheet_is_financial(real_corpora, tmp_path):
    path = write_csv(tmp_path, "q2.csv", "Ticker,Sector,Revenue Growth,Net Margin",
                     ["INFY,IT Services,0.08,0.17", "TCS,IT Services,0.06,0.19",
                      "HDFCBANK,Banking,0.12,0.21"])
    assert sandbox.guess_domain(path)[0] == "financial"


def test_a_lab_sheet_is_medical(real_corpora, tmp_path):
    path = write_csv(tmp_path, "labs.csv", "sample_id,assay,cytokine,concentration,timepoint",
                     ["S-201,ELISA,IL-6,42.1,day 7", "S-202,ELISA,TNF-alpha,13.0,day 14"])
    assert sandbox.guess_domain(path)[0] == "medical"


def test_a_finance_word_doc_is_financial_and_indexed_as_finance(real_corpora, tmp_path):
    """Word documents used to be tagged medical no matter what they said."""
    path = write_docx(tmp_path, "annual.docx", [
        "Revenue increased 12 percent year over year while EBITDA margin contracted "
        "due to higher raw material costs. The board declared an interim dividend."])
    domain, _ = sandbox.guess_domain(path)
    assert domain == "financial"
    assert {u.domain for u in extract_text(str(path), domain=domain)} == {"financial"}


@pytest.mark.parametrize("rows", [
    ["Preheat the oven to 180C and whisk the eggs with sugar",
     "Fold in the flour and bake the sponge for 25 minutes"],
    ["Messi scored twice as Inter Miami beat Orlando 3-1",
     "The striker was substituted in the 85th minute"],
])
def test_off_topic_files_are_refused(real_corpora, tmp_path, rows):
    path = write_csv(tmp_path, "x.csv", "note", rows)
    with pytest.raises(sandbox.SandboxError, match="finance or medical"):
        sandbox.guess_domain(path)


def test_an_empty_file_is_refused(real_corpora, tmp_path):
    path = write_docx(tmp_path, "empty.docx", [])
    with pytest.raises(sandbox.SandboxError):
        sandbox.guess_domain(path)
