from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from realtime_asr.document.models import Document
from realtime_asr.patching.applier import ParagraphApplyResult


class SaveConflictError(RuntimeError):
    pass


@dataclass(slots=True)
class SavePlan:
    path: Path
    mode: str


@dataclass(slots=True)
class SaveResult:
    path: Path
    mode: str


def plan_save(document: Document) -> SavePlan:
    current_path = document.path
    if _should_overwrite_tracked_file(current_path):
        target_path = current_path
        mode = "overwrite"
    else:
        target_path = _export_copy_path(current_path)
        mode = "export_copy"
    _assert_save_target_is_safe(document, target_path=target_path, mode=mode)
    return SavePlan(path=target_path, mode=mode)


def save_document(
    document: Document,
    apply_result: ParagraphApplyResult | None = None,
    plan: SavePlan | None = None,
) -> SaveResult:
    resolved_plan = plan or plan_save(document)
    target_path = resolved_plan.path
    mode = resolved_plan.mode
    serialized = render_document(document, apply_result=apply_result)
    target_path.write_text(serialized, encoding="utf-8")
    document.path = target_path
    document.raw_text = serialized
    return SaveResult(path=target_path, mode=mode)


def render_document(document: Document, apply_result: ParagraphApplyResult | None = None) -> str:
    if document.raw_text and apply_result is not None:
        if apply_result.paragraph_original_text not in document.raw_text:
            raise ValueError("Original paragraph text was not found in the source document.")
        return document.raw_text.replace(
            apply_result.paragraph_original_text,
            apply_result.paragraph_updated_text,
            1,
        )
    blocks = [paragraph.text.rstrip() for paragraph in document.paragraphs]
    return "\n\n".join(blocks).rstrip() + "\n"


def _should_overwrite_tracked_file(path: Path) -> bool:
    try:
        repo_root = _git_repo_root(path.parent)
    except (RuntimeError, subprocess.CalledProcessError):
        return False
    try:
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path.resolve())],
            cwd=repo_root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def _git_repo_root(start_dir: Path) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip()).resolve()


def _export_copy_path(path: Path) -> Path:
    if path.stem.endswith(".reviewed"):
        return path
    return path.with_name(f"{path.stem}.reviewed{path.suffix}")


def _assert_save_target_is_safe(document: Document, *, target_path: Path, mode: str) -> None:
    if mode == "overwrite":
        if target_path.exists():
            current_disk_text = target_path.read_text(encoding="utf-8")
            if current_disk_text != document.raw_text:
                raise SaveConflictError(
                    f"Target file changed on disk since session start: {target_path}"
                )
        return

    if mode == "export_copy":
        if target_path == document.path:
            if target_path.exists():
                current_disk_text = target_path.read_text(encoding="utf-8")
                if current_disk_text != document.raw_text:
                    raise SaveConflictError(
                        f"Target file changed on disk since last save: {target_path}"
                    )
            return
        if target_path.exists():
            raise SaveConflictError(
                f"Export target already exists and was not created by this session: {target_path}"
            )
