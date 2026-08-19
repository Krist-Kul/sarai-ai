"""The transcribe stage, with the models stubbed out.

Loading Typhoon and pyannote in CI is not viable, and the interesting logic here
is not the models: it is ordering, the hallucination guard, progress reporting
and what lands in the database.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import numpy as np
import pytest

from sarai import db, storage
from sarai.models import Job, JobKind, LanguageHint, Meeting, Segment, Stage
from sarai.worker import asr, diarize, stages
from sarai.worker.diarize import Turn

SR = 16_000


@pytest.fixture
def job_with_wav(sample_mp3: Path) -> tuple[str, Job]:
    """A meeting whose normalized wav is 30s of quiet tone."""
    meeting_id = uuid.uuid4().hex
    with db.connection() as conn:
        db.create_meeting(
            conn,
            Meeting(
                id=meeting_id,
                title="ประชุมทดสอบ",
                source_file="m.mp3",
                audio_path=str(storage.wav_path(meeting_id)),
                language_hint=LanguageHint.TH,
                created_at=db.utcnow(),
            ),
        )
        job = db.create_job(conn, uuid.uuid4().hex, meeting_id, JobKind.TRANSCRIBE)
    return meeting_id, job


def _stub_audio(monkeypatch: pytest.MonkeyPatch, seconds: float = 30.0) -> None:
    samples = np.zeros(int(seconds * SR), dtype=np.float32)
    monkeypatch.setattr(stages, "read_wav", lambda _wav: (samples, SR))


def _stub_turns(monkeypatch: pytest.MonkeyPatch, turns: list[Turn]) -> None:
    monkeypatch.setattr(diarize, "diarize", lambda _wav, _samples, _sr: turns)


def _stub_asr(monkeypatch: pytest.MonkeyPatch, texts: list[str]) -> None:
    remaining = list(texts)
    monkeypatch.setattr(
        asr,
        "transcribe",
        lambda _clip, _hint, _prompt=None: asr.Transcription(text=remaining.pop(0), confidence=0.9),
    )


def _run(conn: sqlite3.Connection, job: Job) -> list[Segment]:
    return stages.diarize_and_transcribe(conn, job, Path("unused.wav"))


def test_segments_are_chronological_and_numbered(
    job_with_wav: tuple[str, Job], monkeypatch: pytest.MonkeyPatch
) -> None:
    meeting_id, job = job_with_wav
    _stub_audio(monkeypatch)
    _stub_turns(
        monkeypatch,
        [
            Turn(0.0, 4.0, "SPEAKER_00"),
            Turn(4.5, 9.0, "SPEAKER_01"),
            Turn(9.5, 14.0, "SPEAKER_00"),
        ],
    )
    _stub_asr(monkeypatch, ["สวัสดีครับ ประชุมวันนี้", "ผมขอเริ่มที่ deploy", "ตกลงตามนี้ครับ"])

    with db.connection() as conn:
        segments = _run(conn, job)

        assert [s.id for s in segments] == [0, 1, 2]
        assert [s.start for s in segments] == [0.0, 4.5, 9.5]
        assert [s.speaker for s in segments] == ["SPEAKER_00", "SPEAKER_01", "SPEAKER_00"]

        stored = db.get_transcript(conn, meeting_id)
        assert stored is not None
        assert stored.edited is False
        assert [s.text for s in stored.segments] == [s.text for s in segments]
        # Speaker keys start as their own labels; the review screen renames them.
        assert stored.speakers == {"SPEAKER_00": "SPEAKER_00", "SPEAKER_01": "SPEAKER_01"}


def test_code_switching_is_preserved_verbatim(
    job_with_wav: tuple[str, Job], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, job = job_with_wav
    mixed = "เดี๋ยวผม deploy ขึ้น staging ก่อนนะครับ ถ้า QA ผ่านค่อย release"
    _stub_audio(monkeypatch)
    _stub_turns(monkeypatch, [Turn(0.0, 6.0, "SPEAKER_00")])
    _stub_asr(monkeypatch, [mixed])

    with db.connection() as conn:
        segments = _run(conn, job)
    assert segments[0].text == mixed


def test_hallucinated_turns_are_dropped_but_ids_stay_dense(
    job_with_wav: tuple[str, Job], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, job = job_with_wav
    _stub_audio(monkeypatch)
    _stub_turns(
        monkeypatch,
        [
            Turn(0.0, 4.0, "SPEAKER_00"),
            Turn(4.0, 8.0, "SPEAKER_00"),  # repetition loop -> dropped
            Turn(8.0, 12.0, "SPEAKER_01"),
        ],
    )
    _stub_asr(monkeypatch, ["เริ่มประชุมครับ", "ครับ ครับ ครับ ครับ ครับ", "จบการประชุมครับ"])

    with db.connection() as conn:
        segments = _run(conn, job)

    assert [s.id for s in segments] == [0, 1]
    assert [s.text for s in segments] == ["เริ่มประชุมครับ", "จบการประชุมครับ"]


def test_a_fully_hallucinated_recording_fails_loudly(
    job_with_wav: tuple[str, Job], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, job = job_with_wav
    _stub_audio(monkeypatch)
    _stub_turns(monkeypatch, [Turn(0.0, 4.0, "SPEAKER_00"), Turn(4.0, 8.0, "SPEAKER_00")])
    _stub_asr(monkeypatch, ["ครับ ครับ ครับ ครับ", ""])

    with db.connection() as conn, pytest.raises(RuntimeError, match="no intelligible speech"):
        _run(conn, job)


def test_silence_with_no_turns_fails_loudly(
    job_with_wav: tuple[str, Job], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, job = job_with_wav
    _stub_audio(monkeypatch)
    _stub_turns(monkeypatch, [])

    with db.connection() as conn, pytest.raises(RuntimeError, match="No speech detected"):
        _run(conn, job)


def test_progress_advances_and_ends_on_the_transcribing_stage(
    job_with_wav: tuple[str, Job], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, job = job_with_wav
    turns = [Turn(float(i), float(i) + 0.9, "SPEAKER_00") for i in range(12)]
    _stub_audio(monkeypatch)
    _stub_turns(monkeypatch, turns)
    _stub_asr(monkeypatch, [f"ประโยคที่ {i}" for i in range(12)])

    with db.connection() as conn:
        _run(conn, job)
        updated = db.get_job(conn, job.id)

    assert updated is not None
    assert updated.stage is Stage.TRANSCRIBING  # run_transcribe_job sets the terminal stage
    assert updated.detail == "12/12 turns"
    assert updated.progress == pytest.approx(1.0)


def test_degraded_diarization_labels_everything_speaker_00(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No usable pyannote weights: one speaker, but still a usable transcript."""
    monkeypatch.setattr(diarize, "load_pipeline", lambda: None)
    samples = np.zeros(int(50 * SR), dtype=np.float32)

    turns = diarize.diarize(Path("unused.wav"), samples, SR)

    assert {t.speaker for t in turns} == {"SPEAKER_00"}
    assert turns[0].start == 0.0
    assert turns[-1].end == pytest.approx(50.0)
    # A 50s file still gets split, so no single ASR call exceeds the 30s window.
    assert all(t.duration <= diarize.MAX_TURN_SECONDS for t in turns)


def _meeting(auto_summarize: bool) -> tuple[str, Job]:
    meeting_id = uuid.uuid4().hex
    with db.connection() as conn:
        db.create_meeting(
            conn,
            Meeting(
                id=meeting_id,
                title="ประชุมอัตโนมัติ",
                source_file="m.mp3",
                audio_path=str(storage.wav_path(meeting_id)),
                auto_summarize=auto_summarize,
                created_at=db.utcnow(),
            ),
        )
        job = db.create_job(conn, uuid.uuid4().hex, meeting_id, JobKind.TRANSCRIBE)
    return meeting_id, job


def test_auto_summarize_queues_minutes_and_the_ui_follows_the_new_job() -> None:
    meeting_id, job = _meeting(auto_summarize=True)

    with db.connection() as conn:
        db.update_job(conn, job.id, stage=Stage.AWAITING_REVIEW, progress=1.0, release=True)
        summarize_id = stages.chain_summarize(conn, job)
        detail = db.get_meeting_detail(conn, meeting_id)

    assert summarize_id is not None
    # The meeting page watches the latest job per meeting; it has to be this one.
    assert detail is not None
    assert detail.job_id == summarize_id
    assert detail.stage is Stage.QUEUED


def test_review_first_upload_queues_nothing() -> None:
    _, job = _meeting(auto_summarize=False)

    with db.connection() as conn:
        assert stages.chain_summarize(conn, job) is None


def test_auto_summarize_is_ignored_when_the_llm_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A queued job that can only fail is worse than parking at awaiting_review."""
    _, job = _meeting(auto_summarize=True)
    monkeypatch.setenv("LLM_ENABLED", "false")
    get_settings.cache_clear()

    with db.connection() as conn:
        assert stages.chain_summarize(conn, job) is None
