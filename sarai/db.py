"""SQLite access layer.

stdlib sqlite3, WAL, plain SQL. No ORM. Every function here takes an explicit
connection so callers control transaction scope, with `connection()` as the
short-lived default for request handlers.

The jobs table is the queue. See `claim_job` for the claim protocol.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sarai.config import get_settings
from sarai.models import (
    Attendee,
    Job,
    JobKind,
    LanguageHint,
    Meeting,
    MeetingDetail,
    MeetingListItem,
    MinutesJSON,
    Segment,
    Stage,
    SummaryResponse,
    TranscriptResponse,
)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def utcnow() -> str:
    """UTC, second resolution, matching sqlite's datetime('now') format."""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


def _parse_ts(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# Connections and migrations
# ---------------------------------------------------------------------------


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path is not None else get_settings().db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: FastAPI resolves sync dependencies in a worker
    # thread and then runs async handlers on the event loop thread, so one
    # request legitimately touches its connection from two threads -- but never
    # concurrently, and never shared between requests.
    conn = sqlite3.connect(db_path, timeout=5.0, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def connection(path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    """Apply numbered .sql files in order. Applied names are recorded, never re-run."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "  name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    done = {r["name"] for r in conn.execute("SELECT name FROM schema_migrations")}
    applied: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in done:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
            (path.name, utcnow()),
        )
        applied.append(path.name)
    return applied


def init_db(path: Path | str | None = None) -> list[str]:
    with connection(path) as conn:
        return run_migrations(conn)


# ---------------------------------------------------------------------------
# Row hydration
# ---------------------------------------------------------------------------


def _meeting_from_row(row: sqlite3.Row) -> Meeting:
    return Meeting(
        id=row["id"],
        title=row["title"],
        meeting_date=row["meeting_date"],
        source_file=row["source_file"],
        audio_path=row["audio_path"],
        duration_sec=row["duration_sec"],
        language_hint=LanguageHint(row["language_hint"]),
        glossary=json.loads(row["glossary"] or "[]"),
        attendees=[Attendee.model_validate(a) for a in json.loads(row["attendees"] or "[]")],
        created_at=row["created_at"],
    )


def _job_from_row(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        meeting_id=row["meeting_id"],
        kind=JobKind(row["kind"]),
        stage=Stage(row["stage"]),
        progress=row["progress"],
        detail=row["detail"],
        error=row["error"],
        attempts=row["attempts"],
        claimed_by=row["claimed_by"],
        claimed_at=row["claimed_at"],
        updated_at=row["updated_at"],
    )


# ---------------------------------------------------------------------------
# Meetings
# ---------------------------------------------------------------------------


def create_meeting(conn: sqlite3.Connection, meeting: Meeting) -> Meeting:
    conn.execute(
        """INSERT INTO meetings (id, title, meeting_date, source_file, audio_path,
                                 duration_sec, language_hint, glossary, attendees, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            meeting.id,
            meeting.title,
            meeting.meeting_date,
            meeting.source_file,
            meeting.audio_path,
            meeting.duration_sec,
            meeting.language_hint.value,
            json.dumps(meeting.glossary, ensure_ascii=False),
            json.dumps([a.model_dump() for a in meeting.attendees], ensure_ascii=False),
            meeting.created_at,
        ),
    )
    return meeting


def get_meeting(conn: sqlite3.Connection, meeting_id: str) -> Meeting | None:
    row = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
    return _meeting_from_row(row) if row else None


def set_meeting_audio(
    conn: sqlite3.Connection, meeting_id: str, audio_path: str, duration_sec: float | None
) -> None:
    conn.execute(
        "UPDATE meetings SET audio_path = ?, duration_sec = ? WHERE id = ?",
        (audio_path, duration_sec, meeting_id),
    )


def _latest_job_rows(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    """Most recently updated job per meeting -- that's the one the UI cares about."""
    rows = conn.execute(
        """SELECT j.* FROM jobs j
           JOIN (SELECT meeting_id, MAX(updated_at) AS m, MAX(rowid) AS r
                 FROM jobs GROUP BY meeting_id) t
             ON j.meeting_id = t.meeting_id AND j.updated_at = t.m
           ORDER BY j.rowid"""
    ).fetchall()
    return {r["meeting_id"]: r for r in rows}


def list_meetings(conn: sqlite3.Connection) -> list[MeetingListItem]:
    meetings = [
        _meeting_from_row(r)
        for r in conn.execute("SELECT * FROM meetings ORDER BY created_at DESC, rowid DESC")
    ]
    jobs = _latest_job_rows(conn)
    with_transcript = {r["meeting_id"] for r in conn.execute("SELECT meeting_id FROM transcripts")}
    with_summary = {r["meeting_id"] for r in conn.execute("SELECT meeting_id FROM summaries")}
    items: list[MeetingListItem] = []
    for m in meetings:
        job = jobs.get(m.id)
        items.append(
            MeetingListItem(
                meeting=m,
                stage=Stage(job["stage"]) if job else None,
                job_id=job["id"] if job else None,
                progress=job["progress"] if job else 0.0,
                has_transcript=m.id in with_transcript,
                has_summary=m.id in with_summary,
            )
        )
    return items


def get_meeting_detail(conn: sqlite3.Connection, meeting_id: str) -> MeetingDetail | None:
    meeting = get_meeting(conn, meeting_id)
    if meeting is None:
        return None
    row = conn.execute(
        "SELECT * FROM jobs WHERE meeting_id = ? ORDER BY updated_at DESC, rowid DESC LIMIT 1",
        (meeting_id,),
    ).fetchone()
    has_transcript = (
        conn.execute("SELECT 1 FROM transcripts WHERE meeting_id = ?", (meeting_id,)).fetchone()
        is not None
    )
    has_summary = (
        conn.execute("SELECT 1 FROM summaries WHERE meeting_id = ?", (meeting_id,)).fetchone()
        is not None
    )
    return MeetingDetail(
        meeting=meeting,
        stage=Stage(row["stage"]) if row else None,
        job_id=row["id"] if row else None,
        progress=row["progress"] if row else 0.0,
        detail=row["detail"] if row else None,
        error=row["error"] if row else None,
        has_transcript=has_transcript,
        has_summary=has_summary,
    )


def delete_meeting(conn: sqlite3.Connection, meeting_id: str) -> list[str]:
    """Delete all rows for a meeting. Returns file paths the caller must unlink."""
    paths: list[str] = []
    row = conn.execute("SELECT audio_path FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
    if row is None:
        return paths
    if row["audio_path"]:
        paths.append(row["audio_path"])
    paths.extend(
        r["docx_path"]
        for r in conn.execute("SELECT docx_path FROM summaries WHERE meeting_id = ?", (meeting_id,))
        if r["docx_path"]
    )
    with transaction(conn):
        for table in ("summaries", "speakers", "transcripts", "jobs"):
            conn.execute(f"DELETE FROM {table} WHERE meeting_id = ?", (meeting_id,))
        conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
    return paths


# ---------------------------------------------------------------------------
# Jobs / queue
# ---------------------------------------------------------------------------


def create_job(conn: sqlite3.Connection, job_id: str, meeting_id: str, kind: JobKind) -> Job:
    now = utcnow()
    conn.execute(
        """INSERT INTO jobs (id, meeting_id, kind, stage, progress, attempts, updated_at)
           VALUES (?, ?, ?, ?, 0, 0, ?)""",
        (job_id, meeting_id, kind.value, Stage.QUEUED.value, now),
    )
    job = get_job(conn, job_id)
    assert job is not None
    return job


def get_job(conn: sqlite3.Connection, job_id: str) -> Job | None:
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _job_from_row(row) if row else None


def claim_job(conn: sqlite3.Connection, worker_id: str) -> Job | None:
    """Atomically take the oldest queued, unclaimed job.

    One statement, so two workers cannot take the same row: the UPDATE's WHERE
    subquery is evaluated inside the same write transaction that sets claimed_by.
    """
    row = conn.execute(
        """UPDATE jobs SET claimed_by = ?, claimed_at = ?, attempts = attempts + 1,
                           updated_at = ?
           WHERE id = (SELECT id FROM jobs
                       WHERE stage = ? AND claimed_at IS NULL
                       ORDER BY updated_at LIMIT 1)
           RETURNING *""",
        (worker_id, utcnow(), utcnow(), Stage.QUEUED.value),
    ).fetchone()
    return _job_from_row(row) if row else None


def release_stale_claims(conn: sqlite3.Connection, older_than_minutes: int) -> int:
    """Crash recovery: a claim older than the cutoff means the worker died mid-job."""
    cutoff = (datetime.now(UTC) - timedelta(minutes=older_than_minutes)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    cur = conn.execute(
        """UPDATE jobs
           SET claimed_by = NULL, claimed_at = NULL, stage = ?,
               detail = 'reclaimed after worker restart', updated_at = ?
           WHERE claimed_at IS NOT NULL AND claimed_at < ?
             AND stage NOT IN (?, ?, ?)""",
        (
            Stage.QUEUED.value,
            utcnow(),
            cutoff,
            Stage.DONE.value,
            Stage.FAILED.value,
            Stage.AWAITING_REVIEW.value,
        ),
    )
    return cur.rowcount


def claims_by_host(conn: sqlite3.Connection, host: str) -> list[tuple[str, int]]:
    """Non-terminal jobs claimed by a worker on `host`, as (job_id, pid).

    `claimed_by` is "hostname:pid". The caller decides which of those pids are
    still alive -- see `worker.main.recover_local_claims`.
    """
    rows = conn.execute(
        """SELECT id, claimed_by FROM jobs
           WHERE claimed_at IS NOT NULL AND claimed_by LIKE ? AND stage NOT IN (?, ?, ?)""",
        (
            f"{host}:%",
            Stage.DONE.value,
            Stage.FAILED.value,
            Stage.AWAITING_REVIEW.value,
        ),
    ).fetchall()
    out: list[tuple[str, int]] = []
    for row in rows:
        _, _, pid = str(row["claimed_by"]).rpartition(":")
        if pid.isdigit():
            out.append((row["id"], int(pid)))
    return out


def update_job(
    conn: sqlite3.Connection,
    job_id: str,
    *,
    stage: Stage | None = None,
    progress: float | None = None,
    detail: str | None = None,
    error: str | None = None,
    release: bool = False,
) -> None:
    sets: list[str] = ["updated_at = ?"]
    args: list[Any] = [utcnow()]
    if stage is not None:
        sets.append("stage = ?")
        args.append(stage.value)
    if progress is not None:
        sets.append("progress = ?")
        args.append(progress)
    if detail is not None:
        sets.append("detail = ?")
        args.append(detail)
    if error is not None:
        sets.append("error = ?")
        args.append(error)
    if release:
        sets.append("claimed_by = NULL")
        sets.append("claimed_at = NULL")
    args.append(job_id)
    conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", args)


def requeue_job(conn: sqlite3.Connection, job_id: str, detail: str) -> None:
    conn.execute(
        """UPDATE jobs SET stage = ?, claimed_by = NULL, claimed_at = NULL,
                           detail = ?, updated_at = ?
           WHERE id = ?""",
        (Stage.QUEUED.value, detail, utcnow(), job_id),
    )


# ---------------------------------------------------------------------------
# Transcripts and speakers
# ---------------------------------------------------------------------------


def save_transcript(
    conn: sqlite3.Connection, meeting_id: str, segments: list[Segment], *, edited: bool
) -> None:
    payload = json.dumps([s.model_dump() for s in segments], ensure_ascii=False)
    conn.execute(
        """INSERT INTO transcripts (meeting_id, segments, edited) VALUES (?, ?, ?)
           ON CONFLICT(meeting_id) DO UPDATE SET segments = excluded.segments,
                                                 edited = excluded.edited""",
        (meeting_id, payload, int(edited)),
    )


def get_transcript(conn: sqlite3.Connection, meeting_id: str) -> TranscriptResponse | None:
    row = conn.execute(
        "SELECT segments, edited FROM transcripts WHERE meeting_id = ?", (meeting_id,)
    ).fetchone()
    if row is None:
        return None
    segments = [Segment.model_validate(s) for s in json.loads(row["segments"])]
    return TranscriptResponse(
        segments=segments,
        speakers=get_speakers(conn, meeting_id),
        edited=bool(row["edited"]),
    )


def get_speakers(conn: sqlite3.Connection, meeting_id: str) -> dict[str, str]:
    return {
        r["key"]: r["label"]
        for r in conn.execute(
            "SELECT key, label FROM speakers WHERE meeting_id = ? ORDER BY key", (meeting_id,)
        )
    }


def save_speakers(conn: sqlite3.Connection, meeting_id: str, speakers: dict[str, str]) -> None:
    with transaction(conn):
        for key, label in speakers.items():
            conn.execute(
                """INSERT INTO speakers (meeting_id, key, label) VALUES (?, ?, ?)
                   ON CONFLICT(meeting_id, key) DO UPDATE SET label = excluded.label""",
                (meeting_id, key, label),
            )


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------


def save_summary(
    conn: sqlite3.Connection,
    meeting_id: str,
    data: MinutesJSON,
    model: str,
    docx_path: str | None,
) -> None:
    conn.execute(
        """INSERT INTO summaries (meeting_id, data, model, docx_path, created_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(meeting_id) DO UPDATE SET data = excluded.data,
                                                 model = excluded.model,
                                                 docx_path = excluded.docx_path,
                                                 created_at = excluded.created_at""",
        (meeting_id, data.model_dump_json(), model, docx_path, utcnow()),
    )


def get_summary(conn: sqlite3.Connection, meeting_id: str) -> SummaryResponse | None:
    row = conn.execute(
        "SELECT data, model, docx_path, created_at FROM summaries WHERE meeting_id = ?",
        (meeting_id,),
    ).fetchone()
    if row is None:
        return None
    return SummaryResponse(
        data=MinutesJSON.model_validate_json(row["data"]),
        model=row["model"],
        has_document=bool(row["docx_path"]),
        created_at=row["created_at"],
    )


def get_summary_docx_path(conn: sqlite3.Connection, meeting_id: str) -> str | None:
    row = conn.execute(
        "SELECT docx_path FROM summaries WHERE meeting_id = ?", (meeting_id,)
    ).fetchone()
    return row["docx_path"] if row else None


# ---------------------------------------------------------------------------
# Worker heartbeat
# ---------------------------------------------------------------------------


def beat(conn: sqlite3.Connection, pid: str | None = None) -> None:
    conn.execute(
        """INSERT INTO worker_heartbeat (id, pid, beat_at) VALUES (1, ?, ?)
           ON CONFLICT(id) DO UPDATE SET pid = excluded.pid, beat_at = excluded.beat_at""",
        (pid or str(os.getpid()), utcnow()),
    )


def last_beat(conn: sqlite3.Connection) -> tuple[str | None, bool]:
    """Returns (timestamp, alive). Alive means a beat within the last 30 seconds."""
    row = conn.execute("SELECT beat_at FROM worker_heartbeat WHERE id = 1").fetchone()
    if row is None:
        return None, False
    age = (datetime.now(UTC) - _parse_ts(row["beat_at"])).total_seconds()
    return row["beat_at"], age < 30
