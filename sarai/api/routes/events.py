"""Server-sent events for job progress.

The API polls the jobs table; it holds no connection to the worker. That is the
whole point -- the worker stays a plain synchronous process, a restarted API
picks up an in-flight job with no coordination, and two browsers watching the
same job cost two SELECTs a second.

Frame protocol:

    event: job    data: {JobEvent}   on every change
    event: end    data: {JobEvent}   final frame, then the server closes
    event: gone   data: {detail}     the job row vanished mid-stream
    : heartbeat                      comment frame, keeps proxies from timing out

The client closes its EventSource when it sees `end` or `gone`. Without that,
EventSource reconnects on every close and the stream restarts forever.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable

from anyio import to_thread
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from sarai import db
from sarai.models import TERMINAL_STAGES, Job, JobEvent

log = logging.getLogger("sarai.api.events")

router = APIRouter(prefix="/jobs", tags=["jobs"])

POLL_SECONDS = 1.0
HEARTBEAT_SECONDS = 15.0


def _read_job(job_id: str) -> Job | None:
    """Own connection per read. sqlite3 is sync, so this runs in a thread."""
    with db.connection() as conn:
        return db.get_job(conn, job_id)


def _frame(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


def _event_of(job: Job) -> JobEvent:
    return JobEvent(
        job_id=job.id,
        stage=job.stage,
        progress=job.progress,
        detail=job.detail,
        error=job.error,
    )


async def stream_job(
    job_id: str, is_disconnected: Callable[[], Awaitable[bool]]
) -> AsyncIterator[str]:
    """The stream itself. Takes the disconnect check as a callable rather than a
    Request so it can be driven directly in tests -- TestClient buffers whole
    responses, so a live stream cannot be observed through it."""
    last: JobEvent | None = None
    last_write = time.monotonic()

    while True:
        if await is_disconnected():
            log.debug("job=%s client disconnected", job_id)
            return

        job = await to_thread.run_sync(_read_job, job_id)
        if job is None:
            # Deleted while being watched. Named `gone`, not `error`: a
            # server-sent `error` event lands on the same listener EventSource
            # uses for transport failures, and the two mean opposite things.
            yield _frame("gone", f'{{"detail":"Job {job_id} no longer exists"}}')
            return

        event = _event_of(job)
        terminal = job.stage in TERMINAL_STAGES

        if terminal:
            yield _frame("end", event.model_dump_json())
            return
        if event != last:
            yield _frame("job", event.model_dump_json())
            last = event
            last_write = time.monotonic()
        elif time.monotonic() - last_write >= HEARTBEAT_SECONDS:
            yield ": heartbeat\n\n"
            last_write = time.monotonic()

        await asyncio.sleep(POLL_SECONDS)


@router.get("/{job_id}/events")
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    """Stage, progress and detail for one job until it reaches a terminal stage."""
    if await to_thread.run_sync(_read_job, job_id) is None:
        raise HTTPException(404, f"Job {job_id} not found")

    return StreamingResponse(
        stream_job(job_id, request.is_disconnected),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # nginx buffers proxied responses by default, which turns a live
            # stream into one delivery at the end. This disables it.
            "X-Accel-Buffering": "no",
        },
    )
