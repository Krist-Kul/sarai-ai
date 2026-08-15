"""Job claim protocol. This is where subtle bugs hide, so it gets real coverage."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from sarai import db
from sarai.models import Attendee, JobKind, LanguageHint, Meeting, Stage


def _meeting(conn: sqlite3.Connection, title: str = "ประชุมทีม") -> Meeting:
    meeting = Meeting(
        id=uuid.uuid4().hex,
        title=title,
        source_file="a.mp3",
        audio_path="/tmp/a.wav",
        language_hint=LanguageHint.AUTO,
        created_at=db.utcnow(),
    )
    return db.create_meeting(conn, meeting)


def _job(conn: sqlite3.Connection, meeting_id: str) -> str:
    job_id = uuid.uuid4().hex
    db.create_job(conn, job_id, meeting_id, JobKind.TRANSCRIBE)
    return job_id


def test_migrations_are_idempotent() -> None:
    with db.connection() as conn:
        assert db.run_migrations(conn) == []  # conftest already applied them


def test_claim_returns_none_when_queue_empty() -> None:
    with db.connection() as conn:
        assert db.claim_job(conn, "w1") is None


def test_claim_is_exclusive() -> None:
    """Two workers, one queued job: exactly one claim succeeds."""
    with db.connection() as conn:
        meeting = _meeting(conn)
        job_id = _job(conn, meeting.id)

    with db.connection() as a, db.connection() as b:
        first = db.claim_job(a, "worker-a")
        second = db.claim_job(b, "worker-b")

    assert first is not None
    assert first.id == job_id
    assert first.claimed_by == "worker-a"
    assert first.attempts == 1
    assert second is None


def test_claim_is_fifo_by_updated_at() -> None:
    with db.connection() as conn:
        m1, m2 = _meeting(conn, "first"), _meeting(conn, "second")
        older = _job(conn, m1.id)
        newer = _job(conn, m2.id)
        conn.execute("UPDATE jobs SET updated_at = '2020-01-01 00:00:00' WHERE id = ?", (older,))

        assert (claimed := db.claim_job(conn, "w")) is not None
        assert claimed.id == older
        assert (second := db.claim_job(conn, "w")) is not None
        assert second.id == newer


def test_requeue_clears_the_claim() -> None:
    with db.connection() as conn:
        meeting = _meeting(conn)
        job_id = _job(conn, meeting.id)
        assert db.claim_job(conn, "w") is not None

        db.requeue_job(conn, job_id, "retrying after error: boom")
        job = db.get_job(conn, job_id)
        assert job is not None
        assert job.stage is Stage.QUEUED
        assert job.claimed_by is None
        assert db.claim_job(conn, "w2") is not None  # claimable again


def test_stale_claims_are_released_but_finished_jobs_are_not() -> None:
    stale = (datetime.now(UTC) - timedelta(minutes=45)).strftime("%Y-%m-%d %H:%M:%S")
    with db.connection() as conn:
        m1, m2 = _meeting(conn), _meeting(conn)
        crashed = _job(conn, m1.id)
        finished = _job(conn, m2.id)
        conn.execute(
            "UPDATE jobs SET claimed_by='dead', claimed_at=?, stage=? WHERE id=?",
            (stale, Stage.TRANSCRIBING.value, crashed),
        )
        conn.execute(
            "UPDATE jobs SET claimed_by='dead', claimed_at=?, stage=? WHERE id=?",
            (stale, Stage.AWAITING_REVIEW.value, finished),
        )

        assert db.release_stale_claims(conn, 30) == 1

        reclaimed = db.get_job(conn, crashed)
        assert reclaimed is not None
        assert reclaimed.stage is Stage.QUEUED and reclaimed.claimed_at is None

        untouched = db.get_job(conn, finished)
        assert untouched is not None
        assert untouched.stage is Stage.AWAITING_REVIEW


def test_fresh_claims_survive_recovery() -> None:
    with db.connection() as conn:
        meeting = _meeting(conn)
        _job(conn, meeting.id)
        db.claim_job(conn, "alive")
        assert db.release_stale_claims(conn, 30) == 0


def test_update_job_writes_progress_and_error() -> None:
    with db.connection() as conn:
        meeting = _meeting(conn)
        job_id = _job(conn, meeting.id)
        db.update_job(
            conn, job_id, stage=Stage.TRANSCRIBING, progress=0.42, detail="142/380 segments"
        )
        job = db.get_job(conn, job_id)
        assert job is not None
        assert job.stage is Stage.TRANSCRIBING
        assert job.progress == pytest.approx(0.42)
        assert job.detail == "142/380 segments"


def test_meeting_roundtrip_preserves_thai_and_attendees() -> None:
    with db.connection() as conn:
        meeting = Meeting(
            id=uuid.uuid4().hex,
            title="ประชุมประจำสัปดาห์ — Q3 roadmap",
            source_file="เสียง.m4a",
            audio_path="/tmp/x.wav",
            language_hint=LanguageHint.TH,
            glossary=["Sarai", "โครงการเรือดำน้ำ"],
            attendees=[Attendee(name="คุณสมชาย", role="ผู้จัดการ")],
            created_at=db.utcnow(),
        )
        db.create_meeting(conn, meeting)
        loaded = db.get_meeting(conn, meeting.id)
        assert loaded is not None
        assert loaded.title == meeting.title
        assert loaded.glossary == ["Sarai", "โครงการเรือดำน้ำ"]
        assert loaded.attendees[0].name == "คุณสมชาย"
        assert loaded.language_hint is LanguageHint.TH


def test_delete_meeting_removes_all_rows() -> None:
    with db.connection() as conn:
        meeting = _meeting(conn)
        _job(conn, meeting.id)
        db.save_transcript(conn, meeting.id, [], edited=False)
        db.save_speakers(conn, meeting.id, {"SPEAKER_00": "คุณสมชาย"})

        db.delete_meeting(conn, meeting.id)

        assert db.get_meeting(conn, meeting.id) is None
        for table in ("jobs", "transcripts", "speakers", "summaries"):
            count = conn.execute(
                f"SELECT COUNT(*) c FROM {table} WHERE meeting_id = ?", (meeting.id,)
            ).fetchone()["c"]
            assert count == 0, table
