"""Transcript review.

The editor replaces the whole segment list on save rather than patching rows.
Two people editing the same transcript is not a supported scenario, and a
partial patch protocol invites exactly the silent lost update that a full
replace makes impossible.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from sarai import db
from sarai.api.deps import Db, RequiredMeeting
from sarai.models import SpeakersUpdate, TranscriptResponse, TranscriptUpdate

router = APIRouter(prefix="/meetings", tags=["transcript"])


def _require_transcript(conn: Db, meeting_id: str) -> TranscriptResponse:
    transcript = db.get_transcript(conn, meeting_id)
    if transcript is None:
        raise HTTPException(404, "This meeting has no transcript yet")
    return transcript


@router.get("/{meeting_id}/transcript", response_model=TranscriptResponse)
def get_transcript(meeting: RequiredMeeting, conn: Db) -> TranscriptResponse:
    return _require_transcript(conn, meeting.id)


@router.patch("/{meeting_id}/transcript", response_model=TranscriptResponse)
def update_transcript(
    meeting: RequiredMeeting, payload: TranscriptUpdate, conn: Db
) -> TranscriptResponse:
    _require_transcript(conn, meeting.id)
    if not payload.segments:
        raise HTTPException(422, "A transcript cannot be saved empty")

    ids = [s.id for s in payload.segments]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Segment ids must be unique")

    db.save_transcript(conn, meeting.id, payload.segments, edited=True)
    return _require_transcript(conn, meeting.id)


@router.patch("/{meeting_id}/speakers", response_model=dict[str, str])
def update_speakers(meeting: RequiredMeeting, payload: SpeakersUpdate, conn: Db) -> dict[str, str]:
    """Rename speakers. A blank label resets that speaker to its raw key
    (`SPEAKER_00`), which is the only way back after a mistaken rename."""
    transcript = _require_transcript(conn, meeting.id)
    known = {s.speaker for s in transcript.segments}
    unknown = sorted(set(payload.speakers) - known)
    if unknown:
        raise HTTPException(422, f"No such speaker in this transcript: {', '.join(unknown)}")

    cleaned = {key: (label.strip() or key) for key, label in payload.speakers.items()}
    db.save_speakers(conn, meeting.id, cleaned)
    return db.get_speakers(conn, meeting.id)
