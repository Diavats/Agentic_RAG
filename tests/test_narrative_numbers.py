"""Every number in a tabular row must appear verbatim in its narrative.

Found by live-testing: 29 of 42 growth figures in the financial narratives were
mis-scaled ("10.037%" for a raw 10.037, i.e. 1003.7%) because the model
converted fractions to percentages only some of the time. Retrieval and
synthesis cannot repair a wrong number in the source text, so this checks the
persisted units directly. Zero API calls.
"""
import json
import re
from pathlib import Path

import pytest

from src.build_index import normalize_for_bm25

UNIT_FILES = sorted(Path("data/generated").glob("*_units.json"))


def _tabular_units():
    for path in UNIT_FILES:
        for unit in json.loads(path.read_text(encoding="utf-8")):
            if unit["source_type"] == "tabular":
                yield unit


@pytest.mark.parametrize("unit", list(_tabular_units()), ids=lambda u: u["id"])
def test_every_number_is_copied_verbatim(unit):
    numbers = [v for v in unit["metadata"]["extra"].values()
               if isinstance(v, (int, float)) and not isinstance(v, bool)
               and v == v]  # NaN: an empty cell, never shown to the model
    # Same normalization retrieval uses: the model writes minus as U+2013.
    text = normalize_for_bm25(unit["text"])
    wrong = [s for s in (f"{v:.10g}" for v in numbers)
             # "10.037%" contains "10.037" but states a value 100x too small.
             if s not in text or re.search(re.escape(s) + r"\s*(%|percent)", text)]
    assert not wrong, f"missing or turned into a percentage: {wrong}"
