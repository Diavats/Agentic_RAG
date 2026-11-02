"""The blind set's plumbing: zero API calls."""
import json

from src.eval.run_blind import EVAL_DIR, load_blind_questions


def test_every_blind_question_has_a_key_and_the_asker_notes_are_stripped():
    cases = load_blind_questions()
    key = {c["id"] for c in json.loads(
        (EVAL_DIR / "blind_expected.json").read_text(encoding="utf-8"))["cases"]}
    assert [c["id"] for c in cases] == [f"sir_{i}" for i in range(1, 6)] + \
        [f"classmate1_{i}" for i in range(1, 6)]
    assert {c["id"] for c in cases} == key
    # sir_5's note tells the system the answer; it must never be sent.
    assert not any("[" in c["question"] for c in cases)
    assert cases[4]["question"].endswith("during the reported period?")
