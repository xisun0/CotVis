from pathlib import Path

from realtime_asr.document.loader import load_document
from realtime_asr.document.locator import locate_start_paragraph


def test_locate_start_paragraph_by_index(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("Para one.\n\nPara two.", encoding="utf-8")
    document = load_document(path)

    paragraph = locate_start_paragraph(document, paragraph_index=2)

    assert paragraph.index == 2
    assert paragraph.id == "p2"
    assert paragraph.text == "Para two."


def test_locate_start_paragraph_by_match(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("Alpha paragraph.\n\nBeta paragraph.", encoding="utf-8")
    document = load_document(path)

    paragraph = locate_start_paragraph(document, match_text="beta")

    assert paragraph.index == 2
    assert paragraph.id == "p2"


def test_locate_start_paragraph_skips_non_readable_blocks_by_default(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("<div class=\"wrapper\">\n\n# Intro\n\nReadable paragraph.", encoding="utf-8")
    document = load_document(path)

    paragraph = locate_start_paragraph(document)

    assert paragraph.index == 3
    assert paragraph.id == "p3"
    assert paragraph.text == "Readable paragraph."


def test_locate_start_paragraph_prefers_primary_over_secondary(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text(
        "- list item with prose\n\n> quoted material with prose\n\nMain body paragraph starts here.",
        encoding="utf-8",
    )
    document = load_document(path)

    paragraph = locate_start_paragraph(document)

    assert paragraph.id == "p3"
    assert paragraph.reading_priority == "primary"
