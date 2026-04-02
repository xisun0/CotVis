from pathlib import Path

from realtime_asr.document.loader import load_document


def test_load_document_splits_markdown_paragraphs(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("First sentence. Second sentence.\n\nAnother paragraph.", encoding="utf-8")

    document = load_document(path)

    assert len(document.paragraphs) == 2
    assert len(document.readable_paragraphs) == 2
    assert len(document.primary_paragraphs) == 2
    assert document.paragraphs[0].id == "p1"
    assert document.paragraphs[0].kind == "paragraph"
    assert document.paragraphs[0].readable is True
    assert document.paragraphs[0].reading_priority == "primary"
    assert document.paragraphs[0].sentences[0].id == "p1s1"
    assert document.paragraphs[0].sentences[0].text == "First sentence."
    assert document.paragraphs[0].sentences[1].text == "Second sentence."


def test_load_document_marks_html_wrappers_and_headings_as_non_readable(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text(
        "<div class=\"center\">\n\n# Title\n\nActual prose starts here. Another sentence.",
        encoding="utf-8",
    )

    document = load_document(path)

    assert document.paragraphs[0].kind == "html_block"
    assert document.paragraphs[0].readable is False
    assert document.paragraphs[1].kind == "heading"
    assert document.paragraphs[1].readable is False
    assert document.readable_paragraphs[0].text == "Actual prose starts here. Another sentence."


def test_load_document_marks_short_centered_metadata_as_non_readable(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text(
        "**Paper Title**\n\nAuthor One Author Two\n\nMarch 2026\n\nFirst body paragraph.",
        encoding="utf-8",
    )

    document = load_document(path)

    assert document.paragraphs[0].kind == "metadata"
    assert document.paragraphs[1].kind == "metadata"
    assert document.paragraphs[2].kind == "metadata"
    assert document.primary_paragraphs[0].text == "First body paragraph."
    assert document.readable_paragraphs[0].text == "First body paragraph."


def test_load_document_recognizes_list_quote_rule_and_code_fence(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text(
        "- first list item with prose\n\n> quoted material with prose\n\n---\n\n```python\nprint('x')\n```",
        encoding="utf-8",
    )

    document = load_document(path)

    assert document.paragraphs[0].kind == "list_item"
    assert document.paragraphs[0].readable is True
    assert document.paragraphs[0].reading_priority == "secondary"
    assert document.paragraphs[1].kind == "blockquote"
    assert document.paragraphs[1].readable is True
    assert document.paragraphs[1].reading_priority == "secondary"
    assert document.paragraphs[2].kind == "rule"
    assert document.paragraphs[2].readable is False
    assert document.paragraphs[3].kind == "code_fence"
    assert document.paragraphs[3].readable is False


def test_load_document_marks_contact_style_front_matter_as_secondary(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text(
        "Zhiguo He is at Stanford Graduate School of Business (<hezhg@stanford.edu>).\n\nMain narrative paragraph starts here.",
        encoding="utf-8",
    )

    document = load_document(path)

    assert document.paragraphs[0].reading_priority == "secondary"
    assert document.primary_paragraphs[0].text == "Main narrative paragraph starts here."
