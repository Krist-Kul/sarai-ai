"""Minutes: generate, read, edit, download.

Generation is a job because it takes minutes; editing is synchronous because
the user is sitting there and the only slow part -- the LLM -- is not involved.
An edit re-renders the .docx immediately, so the file on disk always matches
what the screen showed.
"""

from __future__ import annotations

import uuid

from anyio import to_thread
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from sarai import db, storage
from sarai.api.deps import Config, Db, RequiredMeeting
from sarai.models import (
    JobKind,
    Meeting,
    MeetingCreated,
    MinutesJSON,
    Stage,
    SummarizeRequest,
    SummaryResponse,
)

router = APIRouter(prefix="/meetings", tags=["summary"])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# A summarize job that is already queued or running should not be duplicated by
# an impatient second click.
ACTIVE_STAGES = frozenset({Stage.QUEUED, Stage.SUMMARIZING, Stage.RENDERING})


def _require_summary(conn: Db, meeting: Meeting) -> SummaryResponse:
    summary = db.get_summary(conn, meeting.id)
    if summary is None:
        raise HTTPException(404, "This meeting has no minutes yet")
    # The editor labels its sections by type, same as the .docx.
    return summary.model_copy(update={"meeting_type": meeting.meeting_type})


@router.post("/{meeting_id}/summarize", response_model=MeetingCreated, status_code=202)
def start_summarize(
    meeting: RequiredMeeting,
    conn: Db,
    settings: Config,
    body: SummarizeRequest | None = Body(default=None),
) -> MeetingCreated:
    if not settings.llm_enabled:
        raise HTTPException(503, "Summarization is disabled (LLM_ENABLED=false)")
    if db.get_transcript(conn, meeting.id) is None:
        raise HTTPException(
            409, "This meeting has no transcript yet. Transcribe it before generating minutes."
        )

    existing = conn.execute(
        """SELECT id, stage FROM jobs
           WHERE meeting_id = ? AND kind = ?
           ORDER BY updated_at DESC, rowid DESC LIMIT 1""",
        (meeting.id, JobKind.SUMMARIZE.value),
    ).fetchone()
    if existing is not None and Stage(existing["stage"]) in ACTIVE_STAGES:
        # Already working on it -- hand back the job the UI should watch.
        return MeetingCreated(meeting_id=meeting.id, job_id=existing["id"])

    job_id = uuid.uuid4().hex
    with db.transaction(conn):
        # Saved before the job is queued, so the worker reads the new type.
        if body is not None and body.meeting_type is not None:
            db.set_meeting_type(conn, meeting.id, body.meeting_type)
        db.create_job(conn, job_id, meeting.id, JobKind.SUMMARIZE)
    return MeetingCreated(meeting_id=meeting.id, job_id=job_id)


@router.get("/{meeting_id}/summary", response_model=SummaryResponse)
def get_summary(meeting: RequiredMeeting, conn: Db) -> SummaryResponse:
    return _require_summary(conn, meeting)


@router.patch("/{meeting_id}/summary", response_model=SummaryResponse)
async def update_summary(
    meeting: RequiredMeeting, payload: MinutesJSON, conn: Db
) -> SummaryResponse:
    """Save the user's edits and re-render the document.

    Rendering is CPU-bound and python-docx is synchronous, so it runs in a
    worker thread -- doing it inline would block every other request for the
    duration.
    """
    current = _require_summary(conn, meeting)

    from sarai import docgen  # imported lazily: the API only needs it on this path

    path, _pdf = await to_thread.run_sync(
        lambda: docgen.render_documents(
            payload,
            storage.docx_path(meeting.id),
            storage.pdf_path(meeting.id),
            model=current.model,
            meeting_type=meeting.meeting_type,
        )
    )
    db.save_summary(conn, meeting.id, payload, current.model, str(path))
    return _require_summary(conn, meeting)


def summary_filename(title: str, ext: str) -> str:
    """`weekly sync` -> `(Summary) weekly sync.pdf`, so a downloaded summary is
    never mistaken for the recording it came from."""
    return f"(Summary) {title}.{ext}"


@router.get("/{meeting_id}/document")
def get_document(meeting: RequiredMeeting, conn: Db) -> FileResponse:
    path = db.get_summary_docx_path(conn, meeting.id)
    if path is None:
        raise HTTPException(404, "This meeting has no rendered document")
    file = storage.docx_path(meeting.id)
    if not file.is_file():
        raise HTTPException(404, "The document is missing from disk; regenerate the minutes")
    # Thai filenames survive the trip: Starlette encodes them per RFC 5987.
    return FileResponse(
        file, media_type=DOCX_MEDIA_TYPE, filename=summary_filename(meeting.title, "docx")
    )


@router.get("/{meeting_id}/pdf")
def get_pdf(meeting: RequiredMeeting, conn: Db) -> FileResponse:
    if db.get_summary_docx_path(conn, meeting.id) is None:
        raise HTTPException(404, "This meeting has no rendered document")
    file = storage.pdf_path(meeting.id)
    if not file.is_file():
        raise HTTPException(404, "The PDF is missing from disk; regenerate the minutes")
    return FileResponse(
        file, media_type="application/pdf", filename=summary_filename(meeting.title, "pdf")
    )
