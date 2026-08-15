"""Request-scoped dependencies."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException

from sarai import db
from sarai.config import Settings, get_settings
from sarai.models import Meeting


def get_db() -> Iterator[sqlite3.Connection]:
    """One short-lived connection per request. WAL makes this cheap."""
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


Db = Annotated[sqlite3.Connection, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


def require_meeting(meeting_id: str, conn: Db) -> Meeting:
    meeting = db.get_meeting(conn, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail=f"Meeting {meeting_id} not found")
    return meeting


RequiredMeeting = Annotated[Meeting, Depends(require_meeting)]
