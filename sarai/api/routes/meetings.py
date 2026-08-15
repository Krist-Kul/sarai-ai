"""Meetings CRUD and upload.

The upload handler streams to disk in chunks. `await file.read()` on a 3-hour
recording pulls 500 MB into the API process's heap and takes it down; this is
the one place in the codebase where the naive version is actively dangerous.
"""

from __future__ import annotations

import json
import uuid

import aiofiles
from anyio import to_thread
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from sarai import audio, db, storage
from sarai.api.deps import Config, Db, RequiredMeeting
from sarai.config import ALLOWED_UPLOAD_EXTENSIONS
from sarai.models import (
    Attendee,
    JobKind,
    LanguageHint,
    Meeting,
    MeetingCreated,
    MeetingDetail,
    MeetingListItem,
)

router = APIRouter(prefix="/meetings", tags=["meetings"])

CHUNK_SIZE = 1024 * 1024  # 1 MiB


def _parse_glossary(raw: list[str]) -> list[str]:
    """Accepts repeated form fields, or one field holding a JSON array."""
    if len(raw) == 1 and raw[0].lstrip().startswith("["):
        try:
            parsed = json.loads(raw[0])
        except json.JSONDecodeError as exc:
            raise HTTPException(400, f"glossary is not valid JSON: {exc.msg}") from exc
        raw = [str(x) for x in parsed]
    return [term.strip() for term in raw if term.strip()]


def _parse_attendees(raw: list[str]) -> list[Attendee]:
    """Each field is either a JSON object, a JSON array, or a bare name."""
    if len(raw) == 1 and raw[0].lstrip().startswith("["):
        try:
            items = json.loads(raw[0])
        except json.JSONDecodeError as exc:
            raise HTTPException(400, f"attendees is not valid JSON: {exc.msg}") from exc
        return [Attendee.model_validate(i) for i in items]

    out: list[Attendee] = []
    for entry in raw:
        text = entry.strip()
        if not text:
            continue
        if text.startswith("{"):
            try:
                out.append(Attendee.model_validate_json(text))
            except ValueError as exc:
                raise HTTPException(400, f"attendee entry is invalid: {text}") from exc
        else:
            out.append(Attendee(name=text))
    return out


@router.post("", response_model=MeetingCreated, status_code=201)
async def create_meeting(
    conn: Db,
    settings: Config,
    file: UploadFile = File(...),
    title: str = Form(...),
    meeting_date: str | None = Form(None),
    language_hint: LanguageHint = Form(LanguageHint.AUTO),
    attendees: list[str] = Form(default=[]),
    glossary: list[str] = Form(default=[]),
) -> MeetingCreated:
    filename = file.filename or "upload"
    ext = storage.safe_extension(filename)
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            415,
            f"Unsupported file type '{ext or filename}'. "
            f"Accepted: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}",
        )
    if not title.strip():
        raise HTTPException(422, "title is required")

    parsed_attendees = _parse_attendees(attendees)
    parsed_glossary = _parse_glossary(glossary)

    settings.ensure_dirs()
    free = await to_thread.run_sync(storage.free_bytes)
    if free < settings.min_free_disk_bytes:
        raise HTTPException(
            507, f"Not enough free disk space ({free // 1024**2} MB) to accept an upload"
        )

    meeting_id = uuid.uuid4().hex
    dest = storage.upload_path(meeting_id, filename)

    written = 0
    try:
        async with aiofiles.open(dest, "wb") as out:
            while chunk := await file.read(CHUNK_SIZE):
                written += len(chunk)
                if written > settings.upload_max_bytes:
                    raise HTTPException(
                        413,
                        f"File exceeds the {settings.upload_max_bytes // 1024**2} MB limit",
                    )
                await out.write(chunk)
        if written == 0:
            raise HTTPException(400, "Uploaded file is empty")

        info = await to_thread.run_sync(audio.probe, dest)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except audio.AudioError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, str(exc)) from exc
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    meeting = Meeting(
        id=meeting_id,
        title=title.strip(),
        meeting_date=meeting_date or None,
        source_file=filename,
        audio_path=str(storage.wav_path(meeting_id)),
        duration_sec=info.duration_sec,
        language_hint=language_hint,
        glossary=parsed_glossary,
        attendees=parsed_attendees,
        created_at=db.utcnow(),
    )
    job_id = uuid.uuid4().hex
    with db.transaction(conn):
        db.create_meeting(conn, meeting)
        db.create_job(conn, job_id, meeting_id, JobKind.TRANSCRIBE)
    return MeetingCreated(meeting_id=meeting_id, job_id=job_id)


@router.get("", response_model=list[MeetingListItem])
def list_meetings(conn: Db) -> list[MeetingListItem]:
    return db.list_meetings(conn)


@router.get("/{meeting_id}", response_model=MeetingDetail)
def get_meeting(meeting_id: str, conn: Db) -> MeetingDetail:
    detail = db.get_meeting_detail(conn, meeting_id)
    if detail is None:
        raise HTTPException(404, f"Meeting {meeting_id} not found")
    return detail


@router.get("/{meeting_id}/audio")
def get_audio(meeting: RequiredMeeting) -> FileResponse:
    """Original upload, for the review screen's player. Local network only."""
    path = storage.find_upload(meeting.id)
    if path is None:
        raise HTTPException(404, "Audio file is missing from disk")
    return FileResponse(path, filename=meeting.source_file)


@router.delete("/{meeting_id}", status_code=204)
def delete_meeting(meeting: RequiredMeeting, conn: Db) -> None:
    extra = db.delete_meeting(conn, meeting.id)
    storage.purge(meeting.id, extra)
