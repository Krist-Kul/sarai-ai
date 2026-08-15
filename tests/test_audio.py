"""ffmpeg wrapper and the normalize stage."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from sarai import audio, db, storage
from sarai.models import JobKind, LanguageHint, Meeting, Stage
from sarai.worker import stages


def test_probe_reads_duration(sample_mp3: Path) -> None:
    info = audio.probe(sample_mp3)
    assert info.duration_sec == pytest.approx(2.0, abs=0.3)
    assert info.channels == 2
    assert info.sample_rate == 44100


def test_probe_rejects_non_media(tmp_path: Path) -> None:
    bad = tmp_path / "x.mp3"
    bad.write_bytes(b"garbage")
    with pytest.raises(audio.AudioError):
        audio.probe(bad)


def test_normalize_produces_16k_mono_wav(sample_mp3: Path, tmp_path: Path) -> None:
    out = audio.normalize(sample_mp3, tmp_path / "out.wav")
    info = audio.probe(out)
    assert info.sample_rate == audio.TARGET_SAMPLE_RATE
    assert info.channels == audio.TARGET_CHANNELS
    assert info.codec == "pcm_s16le"
    assert not (tmp_path / "out.wav.part").exists()  # temp file cleaned up


def test_slice_wav_cuts_the_requested_window(sample_mp3: Path, tmp_path: Path) -> None:
    src = audio.normalize(sample_mp3, tmp_path / "full.wav")
    piece = audio.slice_wav(src, tmp_path / "piece.wav", 0.5, 1.25)
    assert audio.probe(piece).duration_sec == pytest.approx(0.75, abs=0.05)


def test_normalize_stage_records_duration_and_wav_path(sample_mp3: Path) -> None:
    meeting_id = uuid.uuid4().hex
    dest = storage.upload_path(meeting_id, "meeting.mp3")
    dest.write_bytes(sample_mp3.read_bytes())

    with db.connection() as conn:
        db.create_meeting(
            conn,
            Meeting(
                id=meeting_id,
                title="t",
                source_file="meeting.mp3",
                audio_path=str(storage.wav_path(meeting_id)),
                language_hint=LanguageHint.AUTO,
                created_at=db.utcnow(),
            ),
        )
        job = db.create_job(conn, uuid.uuid4().hex, meeting_id, JobKind.TRANSCRIBE)

        wav = stages.normalize(conn, job)

        assert wav.exists()
        assert wav == storage.wav_path(meeting_id)
        meeting = db.get_meeting(conn, meeting_id)
        assert meeting is not None
        assert meeting.audio_path == str(wav)
        assert meeting.duration_sec == pytest.approx(2.0, abs=0.3)

        updated = db.get_job(conn, job.id)
        assert updated is not None and updated.stage is Stage.NORMALIZING


def test_normalize_stage_fails_loudly_when_upload_is_missing() -> None:
    meeting_id = uuid.uuid4().hex
    with db.connection() as conn:
        db.create_meeting(
            conn,
            Meeting(
                id=meeting_id,
                title="t",
                source_file="gone.mp3",
                audio_path=str(storage.wav_path(meeting_id)),
                created_at=db.utcnow(),
            ),
        )
        job = db.create_job(conn, uuid.uuid4().hex, meeting_id, JobKind.TRANSCRIBE)
        with pytest.raises(RuntimeError, match="missing from disk"):
            stages.normalize(conn, job)
