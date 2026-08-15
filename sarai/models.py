"""Shared Pydantic models.

Defined once here, imported by the API, the worker, and scripts/gen_types.py
which emits web/src/types.ts. If a shape crosses a process boundary it belongs
in this file and nowhere else.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LanguageHint(StrEnum):
    AUTO = "auto"
    TH = "th"
    EN = "en"


class JobKind(StrEnum):
    TRANSCRIBE = "transcribe"
    SUMMARIZE = "summarize"


class Stage(StrEnum):
    QUEUED = "queued"
    NORMALIZING = "normalizing"
    DIARIZING = "diarizing"
    TRANSCRIBING = "transcribing"
    AWAITING_REVIEW = "awaiting_review"
    SUMMARIZING = "summarizing"
    RENDERING = "rendering"
    DONE = "done"
    FAILED = "failed"


TERMINAL_STAGES: frozenset[Stage] = frozenset({Stage.AWAITING_REVIEW, Stage.DONE, Stage.FAILED})

# ---------------------------------------------------------------------------
# Core domain
# ---------------------------------------------------------------------------


class Attendee(BaseModel):
    name: str
    role: str | None = None


class Segment(BaseModel):
    id: int
    start: float  # seconds
    end: float
    speaker: str  # "SPEAKER_00"
    text: str
    confidence: float | None = None


class Meeting(BaseModel):
    id: str
    title: str
    meeting_date: str | None = None
    source_file: str
    audio_path: str
    duration_sec: float | None = None
    language_hint: LanguageHint = LanguageHint.AUTO
    glossary: list[str] = Field(default_factory=list)
    attendees: list[Attendee] = Field(default_factory=list)
    created_at: str


class Job(BaseModel):
    id: str
    meeting_id: str
    kind: JobKind
    stage: Stage
    progress: float = 0.0
    detail: str | None = None
    error: str | None = None
    attempts: int = 0
    claimed_by: str | None = None
    claimed_at: str | None = None
    updated_at: str


class MeetingListItem(BaseModel):
    """Row in the meetings list: the meeting plus just enough job state."""

    meeting: Meeting
    stage: Stage | None = None
    job_id: str | None = None
    progress: float = 0.0
    has_transcript: bool = False
    has_summary: bool = False


class MeetingDetail(MeetingListItem):
    error: str | None = None
    detail: str | None = None


# ---------------------------------------------------------------------------
# Requests / responses
# ---------------------------------------------------------------------------


class MeetingCreated(BaseModel):
    meeting_id: str
    job_id: str


class JobEvent(BaseModel):
    """One SSE frame on /api/jobs/:id/events."""

    job_id: str
    stage: Stage
    progress: float
    detail: str | None = None
    error: str | None = None


class TranscriptResponse(BaseModel):
    segments: list[Segment]
    speakers: dict[str, str]  # {"SPEAKER_00": "คุณสมชาย"}
    edited: bool = False


class TranscriptUpdate(BaseModel):
    """Full replace. Partial patches invite lost updates across two editors."""

    segments: list[Segment]


class SpeakersUpdate(BaseModel):
    speakers: dict[str, str]


class HealthResponse(BaseModel):
    api: bool
    db: bool
    worker_heartbeat: str | None = None
    worker_alive: bool = False
    llm: str  # "deepseek" | "anthropic" | "disabled"


class ErrorResponse(BaseModel):
    detail: str


# ---------------------------------------------------------------------------
# Minutes (LLM output contract)
# ---------------------------------------------------------------------------


class DiscussionTopic(BaseModel):
    topic: str
    points: list[str] = Field(default_factory=list)
    speakers: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    decision: str
    rationale: str | None = None


class ActionItem(BaseModel):
    task: str
    owner: str | None = None
    due: str | None = None
    source_quote: str


class MinutesJSON(BaseModel):
    title: str
    meeting_date: str | None = None
    attendees: list[Attendee] = Field(default_factory=list)
    summary: str = ""
    agenda: list[str] = Field(default_factory=list)
    discussion: list[DiscussionTopic] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    next_meeting: str | None = None


class SummaryResponse(BaseModel):
    data: MinutesJSON
    model: str
    has_document: bool = False
    created_at: str


class SummarizeInput(BaseModel):
    """Everything the summarizer sees. Note: no audio, ever."""

    title: str | None = None
    meeting_date: str | None = None
    attendees: list[Attendee] = Field(default_factory=list)
    glossary: list[str] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    speakers: dict[str, str] = Field(default_factory=dict)
