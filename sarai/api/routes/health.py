"""Health. The worker heartbeat is the part that matters -- a job stuck in
`queued` with no heartbeat means the worker is down, not that it is slow."""

from __future__ import annotations

from fastapi import APIRouter

from sarai import db
from sarai.api.deps import Config, Db
from sarai.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(conn: Db, settings: Config) -> HealthResponse:
    try:
        conn.execute("SELECT 1 FROM meetings LIMIT 1").fetchone()
        db_ok = True
    except Exception:
        db_ok = False

    beat_at, alive = db.last_beat(conn) if db_ok else (None, False)
    llm = settings.llm_provider if settings.llm_enabled else "disabled"
    return HealthResponse(api=True, db=db_ok, worker_heartbeat=beat_at, worker_alive=alive, llm=llm)
