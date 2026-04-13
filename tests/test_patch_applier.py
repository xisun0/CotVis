from pathlib import Path
import subprocess

from realtime_asr.document.models import Document, Paragraph, Sentence
from realtime_asr.patching.applier import apply_patch_to_text, apply_sentence_replacement
from realtime_asr.patching.planner import plan_patch
from realtime_asr.patching.save import SaveConflictError, plan_save, render_document, save_document


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


def test_apply_sentence_replacement_updates_targeted_sentence_only() -> None:
    paragraph = Paragraph(
        id="p1",
        index=1,
        kind="paragraph",
        text="First sentence. Second sentence.",
        readable=True,
        reading_priority="primary",
        sentences=[
            Sentence(id="p1s1", index=1, text="First sentence."),
            Sentence(id="p1s2", index=2, text="Second sentence."),
        ],
    )

    result = apply_sentence_replacement(
        paragraph,
        sentence_id="p1s2",
        replacement="Updated second sentence.",
    )

    assert result.original_text == "Second sentence."
    assert result.sentence_id == "p1s2"
    assert paragraph.text == "First sentence. Updated second sentence."
    assert result.paragraph_original_text == "First sentence. Second sentence."
    assert result.paragraph_updated_text == "First sentence. Updated second sentence."
    assert [sentence.text for sentence in paragraph.sentences] == [
        "First sentence.",
        "Updated second sentence.",
    ]


def test_save_document_overwrites_tracked_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)

    path = repo / "draft.md"
    path.write_text("Old sentence.\n", encoding="utf-8")
    subprocess.run(["git", "add", "draft.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    document = Document(
        path=path,
        paragraphs=[
            Paragraph(
                id="p1",
                index=1,
                kind="paragraph",
                text="Old sentence.",
                readable=True,
                reading_priority="primary",
                sentences=[Sentence(id="p1s1", index=1, text="Old sentence.")],
            )
        ],
        raw_text="Old sentence.\n",
    )

    apply_result = apply_sentence_replacement(
        document.paragraphs[0],
        sentence_id="p1s1",
        replacement="New sentence.",
    )
    save_plan = plan_save(document)
    result = save_document(document, apply_result=apply_result, plan=save_plan)

    assert result.mode == "overwrite"
    assert result.path == path
    assert path.read_text(encoding="utf-8") == "New sentence.\n"


def test_save_document_exports_copy_for_untracked_file(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("Old sentence.\n", encoding="utf-8")
    document = Document(
        path=path,
        paragraphs=[
            Paragraph(
                id="p1",
                index=1,
                kind="paragraph",
                text="Old sentence.",
                readable=True,
                reading_priority="primary",
                sentences=[Sentence(id="p1s1", index=1, text="Old sentence.")],
            )
        ],
        raw_text="Old sentence.\n",
    )

    apply_result = apply_sentence_replacement(
        document.paragraphs[0],
        sentence_id="p1s1",
        replacement="New sentence.",
    )
    save_plan = plan_save(document)
    result = save_document(document, apply_result=apply_result, plan=save_plan)

    assert result.mode == "export_copy"
    assert result.path == tmp_path / "draft.reviewed.md"
    assert result.path.read_text(encoding="utf-8") == "New sentence.\n"
    assert document.path == result.path


def test_render_document_joins_blocks_with_blank_lines() -> None:
    document = Document(
        path=Path("draft.md"),
        paragraphs=[
            Paragraph(
                id="p1",
                index=1,
                kind="heading",
                text="# Title",
                readable=False,
                reading_priority="skip",
                sentences=[],
            ),
            Paragraph(
                id="p2",
                index=2,
                kind="paragraph",
                text="Body sentence.",
                readable=True,
                reading_priority="primary",
                sentences=[Sentence(id="p2s1", index=1, text="Body sentence.")],
            ),
        ],
    )

    assert render_document(document) == "# Title\n\nBody sentence.\n"


def test_render_document_replaces_only_target_paragraph_in_raw_text() -> None:
    original = "Line A  \n\nTarget first. Target second.\n\n```python\nprint('x')\n```\n"
    paragraph = Paragraph(
        id="p2",
        index=2,
        kind="paragraph",
        text="Target first. Target second.",
        readable=True,
        reading_priority="primary",
        sentences=[
            Sentence(id="p2s1", index=1, text="Target first."),
            Sentence(id="p2s2", index=2, text="Target second."),
        ],
    )
    apply_result = apply_sentence_replacement(
        paragraph,
        sentence_id="p2s2",
        replacement="Updated second.",
    )
    document = Document(path=Path("draft.md"), paragraphs=[paragraph], raw_text=original)

    rendered = render_document(document, apply_result=apply_result)

    assert rendered == "Line A  \n\nTarget first. Updated second.\n\n```python\nprint('x')\n```\n"


def test_plan_save_rejects_tracked_file_changed_on_disk(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)

    path = repo / "draft.md"
    path.write_text("Old sentence.\n", encoding="utf-8")
    subprocess.run(["git", "add", "draft.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    document = Document(
        path=path,
        paragraphs=[],
        raw_text="Old sentence.\n",
    )
    path.write_text("Externally changed.\n", encoding="utf-8")

    try:
        plan_save(document)
    except SaveConflictError as exc:
        assert "changed on disk" in str(exc)
    else:
        raise AssertionError("Expected SaveConflictError for externally modified tracked file")


def test_plan_save_rejects_existing_export_copy_not_owned_by_session(tmp_path: Path) -> None:
    path = tmp_path / "draft.md"
    path.write_text("Original.\n", encoding="utf-8")
    reviewed = tmp_path / "draft.reviewed.md"
    reviewed.write_text("Other session output.\n", encoding="utf-8")
    document = Document(
        path=path,
        paragraphs=[],
        raw_text="Original.\n",
    )

    try:
        plan_save(document)
    except SaveConflictError as exc:
        assert "Export target already exists" in str(exc)
    else:
        raise AssertionError("Expected SaveConflictError for existing export copy")
