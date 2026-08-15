"""ffmpeg wrapper: probe and normalize.

Shells out rather than binding a library on purpose -- ffmpeg's CLI is the
stable interface, and a broken input fails with a message we can show the user
instead of a segfault inside the API process.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sarai.config import get_settings

TARGET_SAMPLE_RATE = 16_000
TARGET_CHANNELS = 1


class AudioError(RuntimeError):
    """Unreadable or unsupported media. The message is shown to the user."""


@dataclass(frozen=True)
class AudioInfo:
    duration_sec: float | None
    sample_rate: int | None
    channels: int | None
    codec: str | None


def _run(cmd: list[str], *, timeout: float = 3600.0) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise AudioError(f"{cmd[0]} not found on PATH. Install ffmpeg.") from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioError(f"{cmd[0]} timed out after {timeout:.0f}s") from exc


def _tail(text: str, lines: int = 4) -> str:
    return " / ".join(ln.strip() for ln in text.strip().splitlines()[-lines:] if ln.strip())


def probe(path: Path) -> AudioInfo:
    """Read duration and stream properties. Raises AudioError if there is no audio."""
    settings = get_settings()
    proc = _run(
        [
            settings.ffprobe_bin,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-select_streams",
            "a:0",
            str(path),
        ],
        timeout=120.0,
    )
    if proc.returncode != 0:
        raise AudioError(f"Cannot read media file: {_tail(proc.stderr)}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AudioError("ffprobe returned unparseable output") from exc

    streams = data.get("streams") or []
    if not streams:
        raise AudioError("File contains no audio stream")
    stream = streams[0]

    duration_raw = stream.get("duration") or (data.get("format") or {}).get("duration")
    duration = None
    if duration_raw is not None:
        try:
            duration = float(duration_raw)
        except (TypeError, ValueError):
            duration = None

    def _int(value: object) -> int | None:
        if isinstance(value, (int, str)):
            try:
                return int(value)
            except ValueError:
                return None
        return None

    return AudioInfo(
        duration_sec=duration,
        sample_rate=_int(stream.get("sample_rate")),
        channels=_int(stream.get("channels")),
        codec=stream.get("codec_name"),
    )


def normalize(src: Path, dest: Path) -> Path:
    """Transcode to 16 kHz mono 16-bit WAV -- what both pyannote and Whisper want.

    Loudness normalization is deliberately omitted: dynamic range compression on
    a quiet participant helps ASR, but `loudnorm` also lifts the noise floor
    between turns, which is exactly what makes Whisper hallucinate.
    """
    settings = get_settings()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    proc = _run(
        [
            settings.ffmpeg_bin,
            "-nostdin",
            "-y",
            "-i",
            str(src),
            "-vn",
            "-ac",
            str(TARGET_CHANNELS),
            "-ar",
            str(TARGET_SAMPLE_RATE),
            "-acodec",
            "pcm_s16le",
            # The temp name ends in .part, so ffmpeg cannot infer the container.
            "-f",
            "wav",
            str(tmp),
        ]
    )
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise AudioError(f"ffmpeg failed to normalize audio: {_tail(proc.stderr)}")
    tmp.replace(dest)
    return dest


def slice_wav(src: Path, dest: Path, start: float, end: float) -> Path:
    """Cut [start, end) out of a normalized wav. Used for per-turn transcription."""
    settings = get_settings()
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = _run(
        [
            settings.ffmpeg_bin,
            "-nostdin",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(src),
            "-ac",
            str(TARGET_CHANNELS),
            "-ar",
            str(TARGET_SAMPLE_RATE),
            "-acodec",
            "pcm_s16le",
            str(dest),
        ],
        timeout=600.0,
    )
    if proc.returncode != 0:
        raise AudioError(f"ffmpeg failed to slice audio: {_tail(proc.stderr)}")
    return dest
