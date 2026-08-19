"""Minutes endpoints: enqueue, read, edit, download."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from sarai import db, storage
from sarai.api.main import create_app
from sarai.config import get_settings
from sarai.models import JobKind, Meeting, MinutesJSON, Segment, Stage

MINUTES = {
    "title": "ประชุมทีม",
    "meeting_date": "2026-08-14",
    "summary": "สรุป",
    "action_items": [{"task": "ส่งเอกสาร", "owner": "คุณมาลี", "source_quote": "จะส่งให้"}],
}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


def _meeting(mid: str = "m1", *, transcript: bool = True) -> str:
    with db.connection() as conn:
        db.create_meeting(
            conn,
            Meeting(
                id=mid,
                title="ประชุมทีม",
                source_file="a.mp3",
                audio_path="/tmp/a.wav",
                created_at=db.utcnow(),
            ),
        )
        if transcript:
            db.save_transcript(
                conn,
                mid,
                [Segment(id=0, start=0, end=5, speaker="SPEAKER_00", text="จะส่งให้")],
                edited=False,
            )
    return mid


def test_summarize_enqueues_a_job(client: TestClient) -> None:
    mid = _meeting()
    resp = client.post(f"/api/meetings/{mid}/summarize")
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]

    with db.connection() as conn:
        job = db.get_job(conn, job_id)
    assert job is not None
    assert job.kind is JobKind.SUMMARIZE
    assert job.stage is Stage.QUEUED


def test_summarize_reuses_the_job_already_running(client: TestClient) -> None:
    mid = _meeting()
    first = client.post(f"/api/meetings/{mid}/summarize").json()["job_id"]
    second = client.post(f"/api/meetings/{mid}/summarize").json()["job_id"]
    assert first == second


def test_summarize_without_a_transcript_is_rejected(client: TestClient) -> None:
    mid = _meeting("no-transcript", transcript=False)
    resp = client.post(f"/api/meetings/{mid}/summarize")
    assert resp.status_code == 409
    assert "transcript" in resp.json()["detail"]


def test_summarize_is_unavailable_when_the_llm_is_off(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    mid = _meeting()
    monkeypatch.setenv("LLM_ENABLED", "false")
    get_settings.cache_clear()
    try:
        resp = client.post(f"/api/meetings/{mid}/summarize")
        assert resp.status_code == 503
    finally:
        get_settings.cache_clear()


def test_summary_and_document_404_until_minutes_exist(client: TestClient) -> None:
    mid = _meeting()
    assert client.get(f"/api/meetings/{mid}/summary").status_code == 404
    assert client.get(f"/api/meetings/{mid}/document").status_code == 404


def test_editing_the_summary_saves_and_rerenders_the_document(client: TestClient) -> None:
    mid = _meeting()
    with db.connection() as conn:
        db.save_summary(conn, mid, MinutesJSON.model_validate(MINUTES), "deepseek-chat", None)

    edited = dict(MINUTES, summary="สรุปที่แก้ไขแล้ว")
    resp = client.patch(f"/api/meetings/{mid}/summary", json=edited)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["summary"] == "สรุปที่แก้ไขแล้ว"
    assert body["has_document"] is True
    # The model that wrote the minutes is preserved through a user edit.
    assert body["model"] == "deepseek-chat"

    doc = storage.docx_path(mid)
    assert doc.is_file()

    download = client.get(f"/api/meetings/{mid}/document")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )
    assert download.content[:2] == b"PK"  # a .docx is a zip


def test_document_404s_when_the_file_vanished_from_disk(client: TestClient) -> None:
    mid = _meeting()
    with db.connection() as conn:
        db.save_summary(
            conn, mid, MinutesJSON.model_validate(MINUTES), "m", str(storage.docx_path(mid))
        )
    resp = client.get(f"/api/meetings/{mid}/document")
    assert resp.status_code == 404
    assert "regenerate" in resp.json()["detail"]


def test_meeting_detail_reports_summary_presence(client: TestClient) -> None:
    mid = _meeting()
    assert client.get(f"/api/meetings/{mid}").json()["has_summary"] is False
    with db.connection() as conn:
        db.save_summary(conn, mid, MinutesJSON.model_validate(MINUTES), "m", None)
    assert client.get(f"/api/meetings/{mid}").json()["has_summary"] is True
