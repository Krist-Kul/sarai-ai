"""The API process must never be able to import torch.

A model OOM or a multi-gigabyte import inside the web process takes the whole
API down. This test walks every module reachable from sarai/api/ and fails on
any transitive import of a worker-only package.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "sarai" / "api"
FORBIDDEN = {"torch", "torchaudio", "transformers", "pyannote", "accelerate"}

# Modules the API is allowed to reach into. Anything outside this set is not
# followed, which is what keeps the test from walking into the worker.
SHARED_MODULES = {"sarai.models", "sarai.config", "sarai.db", "sarai.audio", "sarai.storage"}


def _module_files() -> list[Path]:
    files = sorted(API_DIR.rglob("*.py"))
    files += [ROOT / Path(m.replace(".", "/")).with_suffix(".py") for m in SHARED_MODULES]
    return [f for f in files if f.exists()]


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("path", _module_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_ml_imports(path: Path) -> None:
    offending = _imported_roots(path) & FORBIDDEN
    assert not offending, f"{path.relative_to(ROOT)} imports worker-only package(s): {offending}"


def test_api_does_not_import_worker_package() -> None:
    for path in sorted(API_DIR.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert "sarai.worker" not in source, f"{path.relative_to(ROOT)} imports sarai.worker"


def test_torch_absent_after_importing_api() -> None:
    """Importing the app must not pull torch into sys.modules, even if installed."""
    import subprocess
    import sys

    code = (
        "import sys; import sarai.api.main; "
        "print(','.join(m for m in sys.modules if m.split('.')[0] in "
        f"{sorted(FORBIDDEN)!r}))"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "", f"loaded ML modules: {proc.stdout.strip()}"
