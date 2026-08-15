"""SSE stream on /api/jobs/:id/events.

The live-stream tests drive `events.stream_job` directly. Starlette's TestClient
buffers a whole response before handing it back, so a stream that stays open is
invisible through it -- only the endpoints that close immediately (404, an
already-terminal job) are exercised over HTTP.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sarai import db
from sarai.api.main import create_app
from sarai.api.routes import events
from sarai.models import JobKind, LanguageHint, Meeting, Stage


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(autouse=True)
def fast_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    """A one-second poll makes these tests take minutes. Behaviour is identical."""
    monkeypatch.setattr(events, "POLL_SECONDS", 0.01)
    monkeypatch.setattr(events, "HEARTBEAT_SECONDS", 0.05)


async def _connected() -> bool:
    return False


def _meeting(conn: sqlite3.Connection) -> Meeting:
    meeting = Meeting(
        id=uuid.uuid4().hex,
        title="ประชุมทีม",
        source_file="a.mp3",
        audio_path="/tmp/a.wav",
        language_hint=LanguageHint.AUTO,
        created_at=db.utcnow(),
    )
    return db.create_meeting(conn, meeting)


def _queued_job() -> str:
    with db.connection() as conn:
        meeting = _meeting(conn)
        job_id = uuid.uuid4().hex
        db.create_job(conn, job_id, meeting.id, JobKind.TRANSCRIBE)
    return job_id


def _set(job_id: str, **kwargs: Any) -> None:
    with db.connection() as conn:
        db.update_job(conn, job_id, **kwargs)


def parse_frame(raw: str) -> tuple[str, dict[str, Any] | None]:
    """(event name, parsed data). Comment frames come back as ('comment', None)."""
    name: str | None = None
    data: str | None = None
    for line in raw.splitlines():
        if line.startswith("event: "):
            name = line[len("event: ") :]
        elif line.startswith("data: "):
            data = line[len("data: ") :]
        elif line.startswith(":"):
            return "comment", None
    assert name is not None, raw
    return name, json.loads(data) if data is not None else None


async def drain(stream: AsyncIterator[str], limit: int = 50) -> list[tuple[str, Any]]:
    """Everything the stream yields until it closes itself."""
    out: list[tuple[str, Any]] = []
    async for raw in stream:
        out.append(parse_frame(raw))
        assert len(out) < limit, f"stream did not terminate: {out}"
    return out


async def next_data(stream: AsyncIterator[str]) -> dict[str, Any]:
    """Next non-comment frame's payload, skipping heartbeats."""

    async def pump() -> dict[str, Any]:
        async for raw in stream:
            name, data = parse_frame(raw)
            if name != "comment":
                assert data is not None
                return data
        raise AssertionError("stream closed early")

    return await asyncio.wait_for(pump(), timeout=5)


# --- HTTP surface ----------------------------------------------------------


def test_unknown_job_is_404(client: TestClient) -> None:
    res = client.get("/api/jobs/nope/events")
    assert res.status_code == 404
    assert "nope" in res.json()["detail"]


def test_terminal_job_streams_one_end_frame_over_http(client: TestClient) -> None:
    job_id = _queued_job()
    _set(job_id, stage=Stage.AWAITING_REVIEW, progress=1.0, detail="12 segments")

    with client.stream("GET", f"/api/jobs/{job_id}/events") as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        assert res.headers["cache-control"] == "no-cache, no-transform"
        assert res.headers["x-accel-buffering"] == "no"
        body = "".join(res.iter_text())

    name, data = parse_frame(body.strip())
    assert name == "end"
    assert data == {
        "job_id": job_id,
        "stage": "awaiting_review",
        "progress": 1.0,
        "detail": "12 segments",
        "error": None,
    }


# --- the stream itself -----------------------------------------------------


async def test_failed_job_ends_with_its_error() -> None:
    job_id = _queued_job()
    _set(job_id, stage=Stage.FAILED, error="RuntimeError: ffmpeg exploded")

    frames = await drain(events.stream_job(job_id, _connected))
    assert [n for n, _ in frames] == ["end"]
    assert frames[0][1]["stage"] == "failed"
    assert frames[0][1]["error"] == "RuntimeError: ffmpeg exploded"


async def test_stream_follows_stage_changes_then_closes() -> None:
    """The worker's writes surface as frames, in order, and the stream ends itself."""
    job_id = _queued_job()
    steps = [
        (Stage.NORMALIZING, 0.05, "converting a.mp3"),
        (Stage.DIARIZING, 0.15, "identifying speakers"),
        (Stage.TRANSCRIBING, 0.5, "10/20 turns"),
        (Stage.AWAITING_REVIEW, 1.0, "20 segments ready for review"),
    ]
    stream = events.stream_job(job_id, _connected)

    assert (await next_data(stream))["stage"] == "queued"
    seen: list[dict[str, Any]] = []
    for stage, progress, detail in steps:
        _set(job_id, stage=stage, progress=progress, detail=detail)
        seen.append(await next_data(stream))

    assert [d["stage"] for d in seen] == [s.value for s, _, _ in steps]
    assert [d["detail"] for d in seen] == [d for _, _, d in steps]
    assert [d["progress"] for d in seen] == [p for _, p, _ in steps]
    # Terminal frame closed it; nothing follows.
    assert await drain(stream) == []


async def test_unchanged_job_heartbeats_instead_of_repeating_itself() -> None:
    """A queued job with no worker must not spam identical frames."""
    job_id = _queued_job()
    stream = events.stream_job(job_id, _connected)

    names: list[str] = []

    async def pump() -> None:
        async for raw in stream:
            names.append(parse_frame(raw)[0])
            if names.count("comment") >= 2:
                return

    await asyncio.wait_for(pump(), timeout=5)
    assert names.count("job") == 1  # one frame for the queued state, then silence
    assert names.count("comment") == 2


async def test_job_deleted_mid_stream_emits_gone() -> None:
    job_id = _queued_job()
    stream = events.stream_job(job_id, _connected)
    assert (await next_data(stream))["stage"] == "queued"

    with db.connection() as conn:
        job = db.get_job(conn, job_id)
        assert job is not None
        db.delete_meeting(conn, job.meeting_id)

    frames = await drain(stream)
    assert frames[-1][0] == "gone"
    assert job_id in frames[-1][1]["detail"]


async def test_disconnected_client_stops_the_poll_loop() -> None:
    """A closed tab must not leave a generator polling sqlite forever."""
    job_id = _queued_job()

    async def gone() -> bool:
        return True

    assert await drain(events.stream_job(job_id, gone)) == []
