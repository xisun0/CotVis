from realtime_asr.review.constraints import normalize_constraints
from realtime_asr.review.rewrite import rewrite_text


def test_normalize_constraints_filters_empty_items() -> None:
    assert normalize_constraints([" shorter ", "", "  "]) == ["shorter"]


def test_rewrite_text_returns_placeholder_candidate() -> None:
    candidates = rewrite_text("Example sentence.", "make it shorter")

    assert len(candidates) == 1
    assert candidates[0].text == "Example sentence."
