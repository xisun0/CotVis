from __future__ import annotations

from realtime_asr.patching.planner import TextPatch


def apply_patch_to_text(text: str, patch: TextPatch) -> str:
    if patch.operation != "replace":
        raise ValueError(f"Unsupported patch operation: {patch.operation}")
    if patch.original not in text:
        raise ValueError("Patch target was not found in source text.")
    return text.replace(patch.original, patch.replacement, 1)
