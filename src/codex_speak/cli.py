from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_terminal_broadcast_manager():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = (
        repo_root / "betalab" / "codexapp_server_bridge" / "terminal_broadcast_manager.py"
    )
    module_dir = str(module_path.parent)
    if not module_path.exists():
        raise RuntimeError(
            f"Cannot find terminal broadcast manager at {module_path}. "
            "This command currently expects the repository source tree to be present."
        )
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

    spec = importlib.util.spec_from_file_location(
        "codex_speak._terminal_broadcast_manager",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module from {module_path}.")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = _load_terminal_broadcast_manager()
    return int(module.main())
