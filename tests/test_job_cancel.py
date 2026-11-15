"""Cancelling a job from the web UI: POST /api/jobs/:id/cancel.

The API marks the row failed with CANCELLED_ERROR; the worker notices at its
next write or check and abandons the job without overwriting that state.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from sarai import db
from sarai.api.main import create_app
from sarai.models import CANCELLED_ERROR, JobKind, LanguageHint, Meeting, Stage
from sarai.worker import main as worker_main
from sarai.worker import stages
from sarai.worker.stages import JobCancelled


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


def _job(conn: sqlite3.Connection) -> str:
    meeting = db.create_meeting(
        conn,
        Meeting(
            id=uuid.uuid4().hex,
            title="ประชุม",
            source_file="a.mp3",
            audio_path="/tmp/a.wav",
            language_hint=LanguageHint.AUTO,
            created_at=db.utcnow(),
        ),
    )
    job_id = uuid.uuid4().hex
    db.create_job(conn, job_id, meeting.id, JobKind.TRANSCRIBE)
    return job_id


def test_cancel_queued_job_is_never_claimed(client: TestClient) -> None:
    with db.connection() as conn:
        job_id = _job(conn)

    res = client.post(f"/api/jobs/{job_id}/cancel")
    assert res.status_code == 200
    assert res.json()["stage"] == "failed"
    assert res.json()["error"] == CANCELLED_ERROR

    with db.connection() as conn:
        assert db.claim_job(conn, "host:1") is None


def test_cancel_running_job_stops_worker_progress(client: TestClient) -> None:
    with db.connection() as conn:
        _job(conn)
        job = db.claim_job(conn, "host:1")
        assert job is not None
        stages._progress(conn, job, Stage.TRANSCRIBING, 0.3, "3/10 turns")

    assert client.post(f"/api/jobs/{job.id}/cancel").status_code == 200

    with db.connection() as conn:
        with pytest.raises(JobCancelled):
            stages._progress(conn, job, Stage.TRANSCRIBING, 0.4, "4/10 turns")
        with pytest.raises(JobCancelled):
            stages.check_cancelled(conn, job)
        # A late failure must not replace the cancel message, nor requeue it.
        worker_main.handle_failure(conn, job, RuntimeError("boom"), max_attempts=1)
        db.requeue_job(conn, job.id, "retrying")
        row = db.get_job(conn, job.id)
    assert row is not None
    assert row.stage is Stage.FAILED
    assert row.error == CANCELLED_ERROR
    assert row.claimed_by is None


def test_cancel_finished_job_conflicts(client: TestClient) -> None:
    with db.connection() as conn:
        job_id = _job(conn)
        db.update_job(conn, job_id, stage=Stage.AWAITING_REVIEW, progress=1.0)
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 409


def test_cancel_unknown_job_is_404(client: TestClient) -> None:
    assert client.post(f"/api/jobs/{uuid.uuid4().hex}/cancel").status_code == 404
