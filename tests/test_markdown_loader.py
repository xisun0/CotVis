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
    assert document.paragraphs[1].heading_level == 1
    assert document.paragraphs[1].heading_text == "Title"
    assert document.paragraphs[1].section_marker_label == "1 Title"
    assert document.paragraphs[1].readable is False
    assert document.readable_paragraphs[0].section_marker_label == "1 Title"
    assert document.readable_paragraphs[0].text == "Actual prose starts here. Another sentence."


def test_load_document_marks_short_centered_metadata_as_non_readable(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text(
        "**Paper Title**\n\nAuthor One Author Two\n\nMarch 2026\n\nFirst body paragraph.",
        encoding="utf-8",
    )

    document = load_document(path)

    assert document.paragraphs[0].kind == "metadata"
    assert document.paragraphs[0].heading_text == "Paper Title"
    assert document.paragraphs[1].kind == "metadata"
    assert document.paragraphs[2].kind == "metadata"
    assert document.primary_paragraphs[0].text == "First body paragraph."
    assert document.readable_paragraphs[0].text == "First body paragraph."


def test_load_document_assigns_abstract_marker_and_section_numbers(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text(
        "**Abstract**\n\nAbstract body paragraph.\n\n# Introduction\n\nIntro paragraph.\n\n## Background\n\nBackground paragraph.",
        encoding="utf-8",
    )

    document = load_document(path)

    assert document.paragraphs[0].section_marker_label == "Abstract"
    assert document.paragraphs[1].section_marker_label == "Abstract"
    assert document.paragraphs[2].section_marker_label == "1 Introduction"
    assert document.paragraphs[3].section_marker_label == "1 Introduction"
    assert document.paragraphs[4].section_marker_label == "1.1 Background"
    assert document.paragraphs[5].section_marker_label == "1.1 Background"
    assert document.paragraphs[5].section_path_labels == ["1 Introduction", "1.1 Background"]


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
