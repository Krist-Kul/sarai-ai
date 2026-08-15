"""Where files live on disk.

Paths are derived from the meeting id, never from user input -- an uploaded
filename is attacker-controlled text, not a path component.

    data/uploads/<meeting_id><ext>   original upload, kept for playback
    data/work/<meeting_id>.wav       16 kHz mono, what the models read
    data/docs/<meeting_id>.docx      rendered minutes
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sarai.config import get_settings


def safe_extension(filename: str) -> str:
    """Lowercased suffix of an untrusted filename, or '' if it has none."""
    suffix = Path(filename).suffix.lower()
    return suffix if suffix and len(suffix) <= 10 and suffix.isprintable() else ""


def upload_path(meeting_id: str, filename: str) -> Path:
    return get_settings().uploads_dir / f"{meeting_id}{safe_extension(filename)}"


def find_upload(meeting_id: str) -> Path | None:
    for path in sorted(get_settings().uploads_dir.glob(f"{meeting_id}.*")):
        if path.is_file():
            return path
    return None


def wav_path(meeting_id: str) -> Path:
    return get_settings().work_dir / f"{meeting_id}.wav"


def docx_path(meeting_id: str) -> Path:
    return get_settings().docs_dir / f"{meeting_id}.docx"


def free_bytes() -> int:
    settings = get_settings()
    settings.ensure_dirs()
    return shutil.disk_usage(settings.data_dir).free


def purge(meeting_id: str, extra: list[str] | None = None) -> list[str]:
    """Remove every file belonging to a meeting. Returns what was deleted."""
    settings = get_settings()
    removed: list[str] = []
    candidates: list[Path] = [
        *settings.uploads_dir.glob(f"{meeting_id}.*"),
        *settings.work_dir.glob(f"{meeting_id}*"),
        *settings.docs_dir.glob(f"{meeting_id}*"),
        *[Path(p) for p in (extra or [])],
    ]
    for path in candidates:
        try:
            if path.is_file():
                path.unlink()
                removed.append(str(path))
        except OSError:
            # A file we cannot delete must not block deleting the DB rows;
            # the user asked for the meeting to be gone from the UI.
            continue
    return removed
