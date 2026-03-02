from __future__ import annotations

from realtime_asr.web.layout import place_term_boxes


def test_wordcloud_boxes_stay_inside_container_with_safe_margin() -> None:
    stage_w = 980.0
    stage_h = 620.0
    safe_margin = 24.0
    terms = [
        ("welcome", 360.0, 120.0),
        ("swagat", 220.0, 90.0),
        ("欢迎你来", 280.0, 110.0),
        ("workflow", 160.0, 52.0),
        ("decision making", 170.0, 50.0),
        ("uncertainty", 150.0, 46.0),
        ("metrics", 120.0, 42.0),
        ("context", 110.0, 40.0),
        ("signal", 100.0, 38.0),
        ("model quality", 152.0, 44.0),
        ("term extraction", 170.0, 44.0),
        ("visualization", 165.0, 46.0),
        ("co-occurrence", 172.0, 44.0),
        ("adaptive ranking", 182.0, 44.0),
        ("semantic phrase", 168.0, 44.0),
        ("concept map", 146.0, 42.0),
    ]

    boxes = place_term_boxes(stage_w=stage_w, stage_h=stage_h, terms=terms, safe_margin=safe_margin)

    assert len(boxes) == len(terms)
    for box in boxes:
        assert box.x >= safe_margin
        assert box.y >= safe_margin
        assert box.x + box.w <= stage_w - safe_margin
        assert box.y + box.h <= stage_h - safe_margin


def test_wordcloud_boxes_do_not_overlap_for_fixed_payload() -> None:
    terms = [
        ("welcome", 360.0, 120.0),
        ("swagat", 220.0, 90.0),
        ("欢迎你来", 280.0, 110.0),
        ("workflow", 160.0, 52.0),
        ("decision making", 170.0, 50.0),
        ("uncertainty", 150.0, 46.0),
        ("metrics", 120.0, 42.0),
        ("context", 110.0, 40.0),
        ("signal", 100.0, 38.0),
        ("model quality", 152.0, 44.0),
        ("term extraction", 170.0, 44.0),
        ("visualization", 165.0, 46.0),
        ("co-occurrence", 172.0, 44.0),
        ("adaptive ranking", 182.0, 44.0),
        ("semantic phrase", 168.0, 44.0),
        ("concept map", 146.0, 42.0),
    ]
    boxes = place_term_boxes(stage_w=980.0, stage_h=620.0, terms=terms, safe_margin=24.0, max_attempts=500)
    assert len(boxes) == len(terms)

    for i in range(len(boxes)):
        a = boxes[i]
        for j in range(i + 1, len(boxes)):
            b = boxes[j]
            overlaps = not (
                a.x + a.w <= b.x
                or b.x + b.w <= a.x
                or a.y + a.h <= b.y
                or b.y + b.h <= a.y
            )
            assert not overlaps, f"boxes overlap: {a.term} vs {b.term}"


def test_wordcloud_layout_is_deterministic() -> None:
    terms = [
        ("welcome", 360.0, 120.0),
        ("swagat", 220.0, 90.0),
        ("欢迎你来", 280.0, 110.0),
        ("workflow", 160.0, 52.0),
        ("decision making", 170.0, 50.0),
        ("uncertainty", 150.0, 46.0),
        ("metrics", 120.0, 42.0),
        ("context", 110.0, 40.0),
    ]
    run_a = place_term_boxes(stage_w=980.0, stage_h=620.0, terms=terms, safe_margin=24.0)
    run_b = place_term_boxes(stage_w=980.0, stage_h=620.0, terms=terms, safe_margin=24.0)
    assert run_a == run_b
