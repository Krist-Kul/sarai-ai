"""Speaker diarization and turn shaping.

pyannote gives us raw speaker turns. Those turns are not directly usable as ASR
input: they arrive fragmented (a single sentence split across three turns by a
breath) and occasionally enormous (one person talking for four minutes). Both
hurt transcription, in opposite ways.

The heavy imports live inside the loader so the pure turn-shaping helpers below
stay importable -- and testable -- without torch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from sarai.config import get_settings

log = logging.getLogger("sarai.worker.diarize")

MERGE_GAP_SECONDS = 0.5
MAX_TURN_SECONDS = 30.0
MIN_TURN_SECONDS = 0.3
# Never split a turn into a fragment shorter than this; below ~1s Whisper has
# too little context and starts inventing filler.
MIN_SPLIT_PIECE_SECONDS = 1.0

_pipeline: Any | None = None
_pipeline_failed = False

GATE_HELP = (
    "Diarization weights are gated. Accept the license on BOTH pages with the account "
    "that issued HF_TOKEN -- the pipeline pulls a separate segmentation model, and the "
    "two repos are gated independently:\n"
    "  https://huggingface.co/pyannote/speaker-diarization-community-1\n"
    "  https://huggingface.co/pyannote/segmentation-3.0\n"
    "Note: pyannote 4.x redirects the older speaker-diarization-3.1 name to "
    "community-1, so a 403 can name a repo you never configured."
)


@dataclass(frozen=True)
class Turn:
    start: float
    end: float
    speaker: str

    @property
    def duration(self) -> float:
        return self.end - self.start


def resolve_device() -> str:
    """auto -> cuda, then mps, then cpu."""
    import torch

    configured = get_settings().asr_device
    if configured != "auto":
        return configured
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_pipeline() -> Any | None:
    """Load pyannote once into a module global.

    Returns None -- degraded, single-speaker mode -- when there is no HF token or
    when the gated weights cannot be fetched. Transcription is the valuable part
    of this pipeline; losing speaker labels must not cost the user their
    transcript, and the review screen lets them assign speakers by hand.
    """
    global _pipeline, _pipeline_failed
    settings = get_settings()
    if not settings.diarization_enabled or _pipeline_failed:
        return None
    if _pipeline is not None:
        return _pipeline

    import torch
    from pyannote.audio import Pipeline

    log.info("loading diarization model %s", settings.diarization_model)
    try:
        # pyannote 3.1 renamed this kwarg from use_auth_token to token.
        pipeline = Pipeline.from_pretrained(settings.diarization_model, token=settings.hf_token)
    except Exception as exc:  # noqa: BLE001 - any load failure degrades the same way
        _pipeline_failed = True
        log.error("could not load %s: %s\n%s", settings.diarization_model, exc, GATE_HELP)
        return None
    if pipeline is None:
        _pipeline_failed = True
        log.error(
            "pyannote returned no pipeline for %s.\n%s", settings.diarization_model, GATE_HELP
        )
        return None
    device = resolve_device()
    # pyannote's own ops are not all implemented on MPS; CPU is correct there.
    pipeline.to(torch.device("cpu" if device == "mps" else device))
    _pipeline = pipeline
    log.info("diarization model ready on %s", "cpu" if device == "mps" else device)
    return _pipeline


# ---------------------------------------------------------------------------
# Turn shaping -- pure functions, no torch
# ---------------------------------------------------------------------------


def merge_turns(turns: list[Turn], gap: float = MERGE_GAP_SECONDS) -> list[Turn]:
    """Join consecutive turns by the same speaker separated by less than `gap`.

    Diarization splits on breaths and short pauses. Transcribing each fragment
    separately loses the sentence context Whisper needs, and produces a
    transcript nobody wants to read.
    """
    if not turns:
        return []
    ordered = sorted(turns, key=lambda t: (t.start, t.end))
    merged = [ordered[0]]
    for turn in ordered[1:]:
        last = merged[-1]
        if turn.speaker == last.speaker and turn.start - last.end < gap:
            merged[-1] = Turn(last.start, max(last.end, turn.end), last.speaker)
        else:
            merged.append(turn)
    return merged


def quietest_offset(energy: np.ndarray, sample_rate: int, lo: float, hi: float) -> float | None:
    """Offset (seconds, relative to `energy`'s start) of the quietest window in
    [lo, hi]. Returns None when the window is empty."""
    lo_idx = max(0, int(lo * sample_rate))
    hi_idx = min(len(energy), int(hi * sample_rate))
    if hi_idx <= lo_idx:
        return None
    window = energy[lo_idx:hi_idx]
    return float((lo_idx + int(np.argmin(window))) / sample_rate)


def split_long_turn(
    turn: Turn,
    energy: np.ndarray | None,
    sample_rate: int,
    max_len: float = MAX_TURN_SECONDS,
) -> list[Turn]:
    """Recursively split a turn longer than `max_len` at its quietest point.

    Splitting mid-word costs a word; splitting at silence costs nothing. When no
    energy envelope is available we fall back to a hard cut at max_len.
    """
    if turn.duration <= max_len:
        return [turn]

    # Search the middle of the turn so each half stays usefully long.
    lo = max(MIN_SPLIT_PIECE_SECONDS, turn.duration * 0.4)
    hi = min(turn.duration - MIN_SPLIT_PIECE_SECONDS, turn.duration * 0.6)
    offset = None
    if energy is not None and hi > lo:
        offset = quietest_offset(energy, sample_rate, lo, hi)
    if offset is None:
        offset = min(max_len, turn.duration / 2)

    cut = turn.start + offset
    left = Turn(turn.start, cut, turn.speaker)
    right = Turn(cut, turn.end, turn.speaker)
    return [
        *split_long_turn(left, energy, sample_rate, max_len),
        *split_long_turn(right, energy, sample_rate, max_len),
    ]


def rms_envelope(samples: np.ndarray, sample_rate: int, window_ms: int = 30) -> np.ndarray:
    """Per-sample smoothed energy, used only to find quiet points."""
    window = max(1, int(sample_rate * window_ms / 1000))
    squared = np.square(samples.astype(np.float32))
    kernel = np.ones(window, dtype=np.float32) / window
    return np.convolve(squared, kernel, mode="same")


def shape_turns(turns: list[Turn], samples: np.ndarray | None, sample_rate: int) -> list[Turn]:
    """merge -> split -> drop scraps. The order matters: merging first means a
    long turn is only split once, at a real silence rather than at a breath."""
    merged = merge_turns(turns)
    energy = rms_envelope(samples, sample_rate) if samples is not None else None
    shaped: list[Turn] = []
    for turn in merged:
        relative_energy = None
        if energy is not None:
            lo = max(0, int(turn.start * sample_rate))
            hi = min(len(energy), int(turn.end * sample_rate))
            if hi > lo:
                relative_energy = energy[lo:hi]
        shaped.extend(split_long_turn(turn, relative_energy, sample_rate))
    return [t for t in shaped if t.duration >= MIN_TURN_SECONDS]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def to_annotation(result: Any) -> Any:
    """Unwrap whatever the installed pyannote returns into an Annotation.

    pyannote 3 returned an Annotation directly; 4 returns a DiarizeOutput
    carrying two of them. We want the exclusive one: the overlapping variant
    assigns simultaneous speech to several speakers at once, which would send
    the same audio through ASR once per speaker.
    """
    for attribute in ("exclusive_speaker_diarization", "speaker_diarization"):
        annotation = getattr(result, attribute, None)
        if annotation is not None:
            return annotation
    return result


def pipeline_input(wav: Path, samples: np.ndarray | None, sample_rate: int) -> Any:
    """Feed pyannote the decoded waveform rather than a path.

    Handing it a path makes pyannote 4 decode the file itself through
    torchcodec, which dynamically links against whatever FFmpeg build it finds
    and fails hard when that resolves to a different install than the one on
    PATH. We already decoded this file with soundfile, so passing the samples
    skips a second decode and the entire torchcodec dependency.
    """
    import torch

    if samples is None:
        return str(wav)
    waveform = torch.from_numpy(np.ascontiguousarray(samples, dtype=np.float32))
    return {"waveform": waveform.unsqueeze(0), "sample_rate": sample_rate}


def diarize(wav: Path, samples: np.ndarray | None, sample_rate: int) -> list[Turn]:
    """Speaker turns for a normalized wav, already merged, split and filtered.

    With no HF token the whole file becomes one SPEAKER_00 turn: transcription
    still works, speaker attribution is simply unavailable.
    """
    pipeline = load_pipeline()
    if pipeline is None:
        duration = len(samples) / sample_rate if samples is not None else 0.0
        log.warning(
            "diarization unavailable; attributing all speech to SPEAKER_00. "
            "Speakers can still be assigned by hand on the review screen."
        )
        return shape_turns([Turn(0.0, duration, "SPEAKER_00")], samples, sample_rate)

    annotation = to_annotation(pipeline(pipeline_input(wav, samples, sample_rate)))
    raw = [
        Turn(float(segment.start), float(segment.end), str(speaker))
        for segment, _, speaker in annotation.itertracks(yield_label=True)
    ]
    log.info("diarization produced %d raw turns", len(raw))
    shaped = shape_turns(raw, samples, sample_rate)
    speakers = sorted({t.speaker for t in shaped})
    log.info("shaped into %d turns across %d speaker(s): %s", len(shaped), len(speakers), speakers)
    return shaped
