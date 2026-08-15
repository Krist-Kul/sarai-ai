"""Restart recovery.

`release_stale_claims` covers a host that vanished. This covers the common
case: the worker on this machine was killed mid-job and came straight back.
Waiting out the 30-minute stale window there would strand the job.
"""

from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import uuid

from sarai import db
from sarai.models import JobKind, LanguageHint, Meeting, Stage
from sarai.worker.main import recover_local_claims

HOST = socket.gethostname()


def _job(conn: sqlite3.Connection) -> str:
    meeting = db.create_meeting(
        conn,
        Meeting(
            id=uuid.uuid4().hex,
            title="ประชุมทีม",
            source_file="a.mp3",
            audio_path="/tmp/a.wav",
            language_hint=LanguageHint.AUTO,
            created_at=db.utcnow(),
        ),
    )
    job_id = uuid.uuid4().hex
    db.create_job(conn, job_id, meeting.id, JobKind.TRANSCRIBE)
    return job_id


def _dead_pid() -> int:
    """A pid that is certainly not running: our own child, already reaped."""
    proc = subprocess.Popen(["true"])
    proc.wait()
    return proc.pid


def test_dead_local_claim_is_requeued() -> None:
    with db.connection() as conn:
        job_id = _job(conn)
        claimed = db.claim_job(conn, f"{HOST}:{_dead_pid()}")
        assert claimed is not None
        db.update_job(conn, job_id, stage=Stage.TRANSCRIBING, progress=0.4)

        assert recover_local_claims(conn, HOST) == 1

        job = db.get_job(conn, job_id)
        assert job is not None
        assert job.stage is Stage.QUEUED
        assert job.claimed_by is None
        assert job.claimed_at is None
        assert job.detail == "reclaimed after worker restart"
        # A requeued job is claimable again, which is the whole point.
        assert db.claim_job(conn, f"{HOST}:{os.getpid()}") is not None


def test_live_local_claim_is_left_alone() -> None:
    """A second worker starting on the same host must not steal running work."""
    with db.connection() as conn:
        job_id = _job(conn)
        db.claim_job(conn, f"{HOST}:{os.getpid()}")
        db.update_job(conn, job_id, stage=Stage.TRANSCRIBING)

        assert recover_local_claims(conn, HOST) == 0
        job = db.get_job(conn, job_id)
        assert job is not None
        assert job.stage is Stage.TRANSCRIBING
        assert job.claimed_by == f"{HOST}:{os.getpid()}"


def test_other_hosts_are_not_touched() -> None:
    with db.connection() as conn:
        job_id = _job(conn)
        db.claim_job(conn, "some-other-box:1")
        db.update_job(conn, job_id, stage=Stage.DIARIZING)

        assert recover_local_claims(conn, HOST) == 0
        job = db.get_job(conn, job_id)
        assert job is not None
        assert job.stage is Stage.DIARIZING


def test_finished_jobs_are_not_requeued() -> None:
    """awaiting_review is terminal for a transcribe job -- reclaiming it would
    re-run an hour of ASR over a transcript the user is already editing."""
    with db.connection() as conn:
        job_id = _job(conn)
        db.claim_job(conn, f"{HOST}:{_dead_pid()}")
        db.update_job(conn, job_id, stage=Stage.AWAITING_REVIEW, progress=1.0)

        assert recover_local_claims(conn, HOST) == 0
        job = db.get_job(conn, job_id)
        assert job is not None
        assert job.stage is Stage.AWAITING_REVIEW


def test_claims_by_host_ignores_unparseable_worker_ids() -> None:
    with db.connection() as conn:
        job_id = _job(conn)
        db.claim_job(conn, "no-pid-here")
        db.update_job(conn, job_id, stage=Stage.TRANSCRIBING)
        assert db.claims_by_host(conn, "no-pid-here") == []
