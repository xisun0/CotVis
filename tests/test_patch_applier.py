from realtime_asr.patching.applier import apply_patch_to_text
from realtime_asr.patching.planner import plan_patch


def test_apply_patch_replaces_first_match_only() -> None:
    patch = plan_patch(
        target_type="sentence",
        paragraph_id="p1",
        sentence_id="p1s1",
        original="awkward sentence",
        replacement="clear sentence",
    )

    result = apply_patch_to_text(
        "awkward sentence. awkward sentence.",
        patch,
    )

    assert result == "clear sentence. awkward sentence."
    assert patch.target.paragraph_id == "p1"
    assert patch.target.sentence_id == "p1s1"
