"""The heartbeat runs on its own thread.

Before this it was a call at the top of the claim loop, which meant a worker
transcribing a 90-minute recording looked dead to the API for the whole hour --
and the UI told the user no worker was running while their progress bar moved.
"""

from __future__ import annotations

import threading
import time

from sarai import db
from sarai.worker.main import heartbeat_loop


def _wait_for_beat(timeout: float = 5.0) -> tuple[str | None, bool]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with db.connection() as conn:
            beat_at, alive = db.last_beat(conn)
        if beat_at is not None:
            return beat_at, alive
        time.sleep(0.02)
    return None, False


def test_beats_immediately_and_stops_on_the_event() -> None:
    stop = threading.Event()
    thread = threading.Thread(
        target=heartbeat_loop, args=("test-worker:1", stop, 30.0), daemon=True
    )
    thread.start()
    try:
        # The first beat lands before the first sleep: the API must not see a
        # gap while the worker spends minutes loading models.
        beat_at, alive = _wait_for_beat()
        assert beat_at is not None
        assert alive is True
    finally:
        stop.set()
        thread.join(timeout=5.0)

    # A 30-second interval must not hold up shutdown by 30 seconds.
    assert not thread.is_alive()


def test_beat_records_the_worker_id() -> None:
    with db.connection() as conn:
        db.beat(conn, "somehost:4242")
        row = conn.execute("SELECT pid FROM worker_heartbeat WHERE id = 1").fetchone()
    assert row["pid"] == "somehost:4242"
