"""Pipeline stages.

normalize -> diarize -> transcribe -> summarize -> render

Stages are plain synchronous functions. They are CPU/GPU-bound; asyncio here
would buy nothing and make stack traces worse.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import numpy as np

from sarai import audio, db, storage
from sarai.config import get_settings
from sarai.models import Job, Segment, Stage

log = logging.getLogger("sarai.worker.stages")

PROGRESS_EVERY = 10  # turns between job progress writes

# Fractions of the whole job. Diarization is one long opaque pass; transcription
# is the part that reports real per-turn progress.
NORMALIZE_DONE = 0.15
DIARIZE_DONE = 0.25


class StageNotImplemented(RuntimeError):
    """A stage that a later build phase will fill in."""


class StageFailed(RuntimeError):
    """A failure that retrying cannot fix -- a missing API key, a provider
    refusal, a transcript that is not there. Retrying these three times only
    delays the message the user needs to read."""


def _progress(conn: sqlite3.Connection, job: Job, stage: Stage, pct: float, detail: str) -> None:
    db.update_job(conn, job.id, stage=stage, progress=pct, detail=detail)
    log.info("job=%s stage=%s progress=%.2f %s", job.id, stage.value, pct, detail)


def normalize(conn: sqlite3.Connection, job: Job) -> Path:
    """Transcode the original upload to 16 kHz mono WAV and record its duration."""
    meeting = db.get_meeting(conn, job.meeting_id)
    if meeting is None:
        raise RuntimeError(f"Meeting {job.meeting_id} disappeared before normalization")

    src = storage.find_upload(meeting.id)
    if src is None:
        raise RuntimeError(f"Uploaded file for meeting {meeting.id} is missing from disk")

    _progress(conn, job, Stage.NORMALIZING, 0.05, f"converting {meeting.source_file}")
    wav = audio.normalize(src, storage.wav_path(meeting.id))

    info = audio.probe(wav)
    db.set_meeting_audio(conn, meeting.id, str(wav), info.duration_sec)
    _progress(
        conn,
        job,
        Stage.NORMALIZING,
        NORMALIZE_DONE,
        f"{info.duration_sec or 0:.0f}s of audio at 16 kHz mono",
    )
    return wav


def read_wav(wav: Path) -> tuple[np.ndarray, int]:
    """Whole normalized file as float32 mono. 16 kHz mono is ~115 MB per hour,
    which is worth it: slicing in memory beats spawning ffmpeg per turn."""
    import soundfile as sf

    samples, sample_rate = sf.read(str(wav), dtype="float32", always_2d=False)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    return samples, int(sample_rate)


def diarize_and_transcribe(conn: sqlite3.Connection, job: Job, wav: Path) -> list[Segment]:
    """Speaker turns, then one ASR pass per turn, in chronological order."""
    from sarai.worker import asr, diarize

    meeting = db.get_meeting(conn, job.meeting_id)
    if meeting is None:
        raise RuntimeError(f"Meeting {job.meeting_id} disappeared mid-job")

    samples, sample_rate = read_wav(wav)
    prompt = asr.build_prompt(meeting.glossary, [a.name for a in meeting.attendees])
    if prompt:
        log.info("job=%s conditioning ASR on %d glossary term(s)", job.id, len(meeting.glossary))

    _progress(conn, job, Stage.DIARIZING, NORMALIZE_DONE, "identifying speakers")
    turns = diarize.diarize(wav, samples, sample_rate)
    speakers = sorted({t.speaker for t in turns})
    _progress(
        conn,
        job,
        Stage.DIARIZING,
        DIARIZE_DONE,
        f"{len(turns)} turns, {len(speakers)} speaker(s)",
    )
    if not turns:
        raise RuntimeError("No speech detected in this recording")

    segments: list[Segment] = []
    dropped = 0
    total = len(turns)
    _progress(conn, job, Stage.TRANSCRIBING, DIARIZE_DONE, f"0/{total} turns")

    for index, turn in enumerate(turns, start=1):
        lo = max(0, int(turn.start * sample_rate))
        hi = min(len(samples), int(turn.end * sample_rate))
        clip = samples[lo:hi]
        if clip.size == 0:
            dropped += 1
            continue

        result = asr.transcribe(clip, meeting.language_hint, prompt)
        if asr.looks_hallucinated(result.text, turn.duration):
            dropped += 1
            log.debug(
                "job=%s dropped turn %.2f-%.2f as hallucination: %r",
                job.id,
                turn.start,
                turn.end,
                result.text[:80],
            )
        else:
            segments.append(
                Segment(
                    id=len(segments),
                    start=round(turn.start, 3),
                    end=round(turn.end, 3),
                    speaker=turn.speaker,
                    text=result.text,
                    confidence=result.confidence,
                )
            )

        # The user is watching a stepper for several minutes. Silence reads as a
        # hang, and they re-upload.
        if index % PROGRESS_EVERY == 0 or index == total:
            fraction = DIARIZE_DONE + (1.0 - DIARIZE_DONE) * (index / total)
            _progress(conn, job, Stage.TRANSCRIBING, fraction, f"{index}/{total} turns")

    if not segments:
        raise RuntimeError(
            "Every transcribed turn was rejected as silence or repetition. "
            "The recording may contain no intelligible speech."
        )

    log.info(
        "job=%s transcribed %d segments, dropped %d turn(s) by the hallucination guard",
        job.id,
        len(segments),
        dropped,
    )
    db.save_transcript(conn, meeting.id, segments, edited=False)
    db.save_speakers(conn, meeting.id, {s: s for s in speakers})
    return segments


def summarize(conn: sqlite3.Connection, job: Job) -> None:
    """Transcript -> minutes -> .docx.

    Two stages in one job: `summarizing` is the LLM call (or calls, for a long
    meeting), `rendering` is python-docx. They are split because the first can
    take minutes and the second is always quick, and a user watching a stalled
    progress bar deserves to know which one they are waiting on.
    """
    import asyncio

    from sarai import docgen
    from sarai.llm import LLMError, summarize_minutes
    from sarai.models import SummarizeInput

    settings = get_settings()
    meeting = db.get_meeting(conn, job.meeting_id)
    if meeting is None:
        raise RuntimeError(f"Meeting {job.meeting_id} disappeared before summarization")

    transcript = db.get_transcript(conn, meeting.id)
    if transcript is None:
        raise StageFailed(
            "This meeting has no transcript yet. Transcribe it before generating minutes."
        )

    inp = SummarizeInput(
        title=meeting.title,
        meeting_date=meeting.meeting_date,
        attendees=meeting.attendees,
        glossary=meeting.glossary,
        segments=transcript.segments,
        speakers=transcript.speakers,
    )

    _progress(
        conn,
        job,
        Stage.SUMMARIZING,
        0.1,
        f"sending {len(transcript.segments)} segments to {settings.llm_provider}",
    )

    def on_progress(fraction: float, detail: str) -> None:
        # The summarize stage owns 0.1..0.8 of the job; rendering owns the rest.
        _progress(conn, job, Stage.SUMMARIZING, 0.1 + 0.7 * fraction, detail)

    try:
        minutes, model, dropped = asyncio.run(
            summarize_minutes(inp, settings, on_progress=on_progress)
        )
    except LLMError as exc:
        # A provider refusal or a missing key is not worth three retries.
        raise StageFailed(str(exc)) from exc

    if dropped:
        log.warning("job=%s dropped %d action item(s) with unverifiable quotes", job.id, dropped)

    _progress(conn, job, Stage.RENDERING, 0.85, "rendering the .docx")
    path = docgen.render(minutes, storage.docx_path(meeting.id), model=model)
    db.save_summary(conn, meeting.id, minutes, model, str(path))

    detail = f"{len(minutes.action_items)} action item(s)"
    if dropped:
        detail += f", {dropped} dropped for unverifiable quotes"
    _progress(conn, job, Stage.RENDERING, 0.95, detail)


def run_transcribe_job(conn: sqlite3.Connection, job: Job) -> None:
    wav = normalize(conn, job)
    segments = diarize_and_transcribe(conn, job, wav)
    db.update_job(
        conn,
        job.id,
        stage=Stage.AWAITING_REVIEW,
        progress=1.0,
        detail=f"{len(segments)} segments ready for review",
        release=True,
    )


def run_summarize_job(conn: sqlite3.Connection, job: Job) -> None:
    summarize(conn, job)
    db.update_job(conn, job.id, stage=Stage.DONE, progress=1.0, detail="done", release=True)
