from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from sarai import db
from sarai.config import get_settings


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Every test gets its own data dir and database."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    settings.ensure_dirs()
    db.init_db()
    yield tmp_path
    get_settings.cache_clear()


@pytest.fixture
def conn() -> Iterator[object]:
    with db.connection() as c:
        yield c


@pytest.fixture
def sample_mp3(tmp_path: Path) -> Path:
    """Two seconds of a tone, encoded as mp3 -- a real file for the upload path."""
    path = tmp_path / "sample.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-ac",
            "2",
            "-ar",
            "44100",
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    return path
