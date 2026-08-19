"""The summarize job, end to end without a network call."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator

import pytest

from sarai import db, storage
from sarai.models import Job, JobKind, Meeting, Segment, Stage
from sarai.worker import stages


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    with db.connection() as c:
        yield c


def _seed(conn: sqlite3.Connection, *, transcript: bool = True) -> Job:
    db.create_meeting(
        conn,
        Meeting(
            id="m1",
            title="ประชุมทีม",
            meeting_date="2026-08-14",
            source_file="a.mp3",
            audio_path="/tmp/a.wav",
            glossary=["deploy"],
            created_at=db.utcnow(),
        ),
    )
    if transcript:
        db.save_transcript(
            conn,
            "m1",
            [Segment(id=0, start=0, end=5, speaker="SPEAKER_00", text="เดี๋ยวจะส่งให้วันศุกร์")],
            edited=True,
        )
    return db.create_job(conn, "j1", "m1", JobKind.SUMMARIZE)


class StubChat:
    model = "stub-model"

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    async def complete(self, system: str, user: str) -> str:
        return json.dumps(self.payload, ensure_ascii=False)


@pytest.fixture
def stub_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    payload: dict[str, object] = {
        "title": "ชื่อที่โมเดลแต่งเอง",
        "summary": "สรุปการประชุม",
        "action_items": [
            {"task": "ส่งเอกสาร", "owner": "คุณมาลี", "source_quote": "เดี๋ยวจะส่งให้วันศุกร์"},
            {"task": "ยกเลิกสัญญา", "source_quote": "ผมจะยกเลิกสัญญา"},
        ],
    }
    monkeypatch.setattr("sarai.llm.summarize.get_chat", lambda settings: StubChat(payload))


def test_summarize_job_writes_minutes_and_a_document(
    conn: sqlite3.Connection, stub_llm: None
) -> None:
    job = _seed(conn)

    stages.run_summarize_job(conn, job)

    summary = db.get_summary(conn, "m1")
    assert summary is not None
    assert summary.model == "stub-model"
    # The meeting's own title wins over anything the model invented.
    assert summary.data.title == "ประชุมทีม"
    # The unverifiable action item was dropped; the quoted one survived.
    assert [i.task for i in summary.data.action_items] == ["ส่งเอกสาร"]
    assert summary.has_document is True
    assert storage.docx_path("m1").is_file()

    finished = db.get_job(conn, job.id)
    assert finished is not None
    assert finished.stage is Stage.DONE
    assert finished.claimed_by is None


def test_summarize_without_a_transcript_fails_without_retrying(
    conn: sqlite3.Connection, stub_llm: None
) -> None:
    job = _seed(conn, transcript=False)

    with pytest.raises(stages.StageFailed, match="no transcript"):
        stages.run_summarize_job(conn, job)


def test_llm_errors_are_not_retried(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing key or a refusal fails the same way three times; the user
    should read the message now, not in a minute."""
    job = _seed(conn)

    from sarai.llm.client import LLMError

    def boom(settings: object) -> None:
        raise LLMError("DEEPSEEK_API_KEY is not set")

    monkeypatch.setattr("sarai.llm.summarize.get_chat", boom)

    with pytest.raises(stages.StageFailed, match="DEEPSEEK_API_KEY"):
        stages.run_summarize_job(conn, job)
