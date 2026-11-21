"""Worker loop.

    python -m sarai.worker.main

Claims one job at a time, runs it to completion, then polls again. Single
worker per GPU: model weights are loaded once into module globals and the
stages are synchronous.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import sqlite3
import sys
import threading
import time
from pathlib import Path
from types import FrameType

from sarai import db
from sarai.config import Settings, get_settings
from sarai.models import Job, JobKind, Stage
from sarai.worker import stages
from sarai.worker.stages import JobCancelled, StageFailed, StageNotImplemented

log = logging.getLogger("sarai.worker")

_stop = False
_in_job = False
_restart = False

SOURCE_DIR = Path(__file__).resolve().parents[1]  # the sarai package


def source_stamp(root: Path = SOURCE_DIR) -> float:
    """Newest mtime of any .py file under `root`.

    A long-running worker keeps the modules it imported at start, but imports
    some lazily per job. Edit the code under it and a job can mix old and new
    modules -- "cannot import name X" from a file that plainly defines X.
    With WORKER_RELOAD on, a changed stamp restarts the worker between jobs.
    """
    return max((p.stat().st_mtime for p in root.rglob("*.py")), default=0.0)


def _handle_signal(signum: int, frame: FrameType | None) -> None:
    """Finish the job in hand, then exit. Killing mid-transcription wastes minutes.

    Only a running job is worth waiting for. Idle, or still loading/downloading
    models, there is nothing to finish, and swallowing the signal there left
    Ctrl-C doing nothing while a stuck model download logged retries forever.
    A second signal always exits at once.
    """
    global _stop
    if _stop:
        log.warning("signal %s received again; exiting now", signum)
        os._exit(130)
    _stop = True
    if not _in_job:
        log.info("signal %s received; exiting", signum)
        raise SystemExit(0)
    log.info("signal %s received; finishing current job then exiting (repeat to force)", signum)


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def heartbeat_loop(worker: str, stop: threading.Event, interval: float) -> None:
    """Beat on its own connection until told to stop.

    A thread rather than a call in the main loop: transcribing a 90-minute
    recording is one uninterrupted stretch of work, and a heartbeat that only
    lands between jobs makes the API report the worker dead for the entire time
    it is busiest. The UI then tells the user nothing is running while their
    progress bar moves.
    """
    with db.connection() as conn:
        while True:
            try:
                db.beat(conn, worker)
            except Exception:  # noqa: BLE001 - a missed beat must not kill the worker
                log.warning("heartbeat write failed", exc_info=True)
            if stop.wait(interval):
                return


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # someone else's process, but it exists
    return True


def recover_local_claims(conn: sqlite3.Connection, host: str) -> int:
    """Requeue jobs claimed by a dead worker process on this machine.

    The 30-minute stale sweep is for a host that went away entirely. A worker
    that crashes and restarts is back in seconds, and its in-flight job would
    otherwise sit claimed and invisible for the rest of that half hour. Only
    claims whose pid is gone are released, so a second worker on the same host
    keeps the job it is actually running.
    """
    released = 0
    for job_id, pid in db.claims_by_host(conn, host):
        if _pid_alive(pid):
            continue
        log.info("job=%s was claimed by dead pid %s; requeueing", job_id, pid)
        db.requeue_job(conn, job_id, "reclaimed after worker restart")
        released += 1
    return released


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s %(message)s",
        stream=sys.stdout,
    )


def preload_models() -> None:
    """Load ASR and diarization weights before claiming anything.

    Loading lazily inside the first job works, but it charges that user a
    multi-minute cold start they cannot see, and a bad model name or an expired
    HF token then surfaces as a failed job instead of a worker that refuses to
    start.
    """
    if os.environ.get("SARAI_SKIP_PRELOAD") == "1":
        log.warning("SARAI_SKIP_PRELOAD=1; models will load on first job instead")
        return

    from sarai.worker import asr, diarize

    started = time.monotonic()
    label = asr.preload()
    diarize.load_pipeline()
    log.info("models loaded in %.1fs (asr=%s)", time.monotonic() - started, label)


def run_job(conn: sqlite3.Connection, job: Job) -> None:
    started = time.monotonic()
    log.info("job=%s kind=%s meeting=%s claimed", job.id, job.kind.value, job.meeting_id)
    if job.kind is JobKind.TRANSCRIBE:
        stages.run_transcribe_job(conn, job)
    elif job.kind is JobKind.SUMMARIZE:
        stages.run_summarize_job(conn, job)
    else:  # pragma: no cover - enum is exhaustive
        raise RuntimeError(f"Unknown job kind {job.kind}")
    log.info("job=%s finished in %.1fs", job.id, time.monotonic() - started)


def handle_failure(conn: sqlite3.Connection, job: Job, exc: Exception, max_attempts: int) -> None:
    message = f"{type(exc).__name__}: {exc}"
    retryable = not isinstance(exc, StageNotImplemented | StageFailed)
    if retryable and job.attempts < max_attempts:
        log.warning("job=%s attempt %s failed, requeueing: %s", job.id, job.attempts, message)
        db.requeue_job(conn, job.id, f"retrying after error: {message}")
        # Linear backoff. The claim query orders by updated_at, so a requeued
        # job naturally goes to the back of the line; the sleep keeps a
        # deterministically-failing job from spinning the CPU.
        time.sleep(min(30.0, 2.0 * job.attempts))
    else:
        log.error("job=%s failed permanently: %s", job.id, message)
        # active_only: a job cancelled mid-run keeps its "cancelled" message.
        db.update_job(
            conn, job.id, stage=Stage.FAILED, error=message, release=True, active_only=True
        )


def main() -> int:
    _configure_logging()
    settings = get_settings()
    settings.ensure_dirs()
    db.init_db()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    wid = worker_id()
    stop_beating = threading.Event()
    beater = threading.Thread(
        target=heartbeat_loop,
        args=(wid, stop_beating, settings.worker_heartbeat_seconds),
        name="heartbeat",
        daemon=True,
    )
    # Started before the models load: a cold start is minutes long, and the API
    # should report the worker as present throughout it.
    beater.start()

    try:
        _serve(wid, settings)
    except Exception:
        # The heartbeat thread must not outlive a dead claim loop. If it keeps
        # beating -- a library left a non-daemon thread behind, or the process
        # is wedged on exit -- the API reports a live worker and every job
        # sits on "waiting for a free worker" with no hint that nothing will
        # ever claim it.
        log.exception("worker %s crashed; stopping heartbeat", wid)
        return 1
    finally:
        stop_beating.set()
        beater.join(timeout=2.0)
    if _restart:
        log.info("worker %s restarting to load changed code", wid)
        # Same pid, so `uv run` and `make dev` keep tracking it.
        os.execv(sys.executable, [sys.executable, "-m", "sarai.worker.main"])
    log.info("worker %s stopped", wid)
    return 0


def _serve(wid: str, settings: Settings) -> None:
    """Recover old claims, load models, then claim jobs until told to stop."""
    global _in_job, _restart
    with db.connection() as conn:
        released = db.release_stale_claims(conn, settings.worker_stale_claim_minutes)
        released += recover_local_claims(conn, socket.gethostname())
        if released:
            log.info("released %d stale claim(s) from a previous run", released)
        preload_models()
        from sarai.worker import asr

        log.info(
            "worker %s ready (asr=%s backend=%s device=%s diarization=%s llm=%s)",
            wid,
            settings.asr_model,
            asr.resolve_backend(),
            settings.asr_device,
            "on" if settings.diarization_enabled else "off (no HF_TOKEN)",
            settings.llm_provider if settings.llm_enabled else "disabled",
        )

        stamp = source_stamp() if settings.worker_reload else 0.0
        while not _stop:
            if settings.worker_reload and source_stamp() != stamp:
                _restart = True
                return
            job = db.claim_job(conn, wid)
            if job is None:
                time.sleep(settings.worker_poll_seconds)
                continue
            _in_job = True
            try:
                run_job(conn, job)
            except JobCancelled:
                # cancel_job already wrote the final state and released the claim.
                log.info("job=%s cancelled by user; abandoned", job.id)
            except Exception as exc:  # noqa: BLE001 - the loop must survive any job
                handle_failure(conn, job, exc, settings.worker_max_attempts)
            finally:
                _in_job = False


if __name__ == "__main__":
    raise SystemExit(main())
