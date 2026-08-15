"""Upload and meetings CRUD."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from sarai import db, storage
from sarai.api.main import create_app
from sarai.config import get_settings


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


def _upload(client: TestClient, path: Path, **fields: object) -> httpx.Response:
    """Post a multipart upload. List values become repeated form fields."""
    data: dict[str, str | list[str]] = {"title": str(fields.pop("title", "ประชุมทดสอบ"))}
    for key, value in fields.items():
        data[key] = [str(v) for v in value] if isinstance(value, list) else str(value)
    with path.open("rb") as fh:
        response: httpx.Response = client.post(
            "/api/meetings",
            files={"file": (path.name, fh, "audio/mpeg")},
            data=data,
        )
    return response


def test_health_reports_llm_provider(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["api"] is True
    assert body["db"] is True
    assert body["llm"] == "deepseek"
    assert body["worker_alive"] is False


def test_upload_creates_meeting_job_and_file(client: TestClient, sample_mp3: Path) -> None:
    resp = _upload(
        client,
        sample_mp3,
        title="ประชุมทีม Q3",
        meeting_date="2026-08-14",
        language_hint="th",
        attendees=[json.dumps({"name": "คุณสมชาย", "role": "CTO"}), "Alice"],
        glossary=["Sarai", "roadmap"],
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    meeting_id = body["meeting_id"]
    stored = storage.find_upload(meeting_id)
    assert stored is not None and stored.stat().st_size > 0

    detail = client.get(f"/api/meetings/{meeting_id}").json()
    assert detail["meeting"]["title"] == "ประชุมทีม Q3"
    assert detail["meeting"]["language_hint"] == "th"
    assert detail["meeting"]["glossary"] == ["Sarai", "roadmap"]
    assert detail["meeting"]["attendees"] == [
        {"name": "คุณสมชาย", "role": "CTO"},
        {"name": "Alice", "role": None},
    ]
    # Duration is probed at upload time so the list is useful immediately.
    assert detail["meeting"]["duration_sec"] == pytest.approx(2.0, abs=0.3)
    assert detail["stage"] == "queued"
    assert detail["job_id"] == body["job_id"]

    with db.connection() as conn:
        job = db.get_job(conn, body["job_id"])
    assert job is not None and job.kind.value == "transcribe"


def test_list_is_newest_first(client: TestClient, sample_mp3: Path) -> None:
    first = _upload(client, sample_mp3, title="one").json()["meeting_id"]
    with db.connection() as conn:
        conn.execute(
            "UPDATE meetings SET created_at = '2020-01-01 00:00:00' WHERE id = ?", (first,)
        )
    second = _upload(client, sample_mp3, title="two").json()["meeting_id"]

    items = client.get("/api/meetings").json()
    assert [i["meeting"]["id"] for i in items] == [second, first]
    assert items[0]["has_transcript"] is False
    assert items[0]["has_summary"] is False


def test_rejects_unsupported_extension(client: TestClient, tmp_path: Path) -> None:
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    resp = _upload(client, bad)
    assert resp.status_code == 415
    assert "Accepted" in resp.json()["detail"]


def test_rejects_file_without_audio_stream(client: TestClient, tmp_path: Path) -> None:
    """A file with the right extension but garbage content fails at probe."""
    fake = tmp_path / "broken.mp3"
    fake.write_bytes(b"not audio at all" * 100)
    resp = _upload(client, fake)
    assert resp.status_code == 400
    assert storage.find_upload("") is None
    assert list(get_settings().uploads_dir.iterdir()) == []  # partial file cleaned up


def test_rejects_oversized_upload(
    client: TestClient, sample_mp3: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_max_bytes", 1024)
    resp = _upload(client, sample_mp3)
    assert resp.status_code == 413
    assert list(settings.uploads_dir.iterdir()) == []


def test_delete_removes_rows_and_files(client: TestClient, sample_mp3: Path) -> None:
    meeting_id = _upload(client, sample_mp3).json()["meeting_id"]
    wav = storage.wav_path(meeting_id)
    wav.write_bytes(b"RIFF")

    assert client.delete(f"/api/meetings/{meeting_id}").status_code == 204
    assert client.get(f"/api/meetings/{meeting_id}").status_code == 404
    assert storage.find_upload(meeting_id) is None
    assert not wav.exists()


def test_delete_unknown_meeting_is_404(client: TestClient) -> None:
    assert client.delete("/api/meetings/nope").status_code == 404


def test_audio_endpoint_streams_the_original(client: TestClient, sample_mp3: Path) -> None:
    meeting_id = _upload(client, sample_mp3).json()["meeting_id"]
    resp = client.get(f"/api/meetings/{meeting_id}/audio")
    assert resp.status_code == 200
    assert len(resp.content) == sample_mp3.stat().st_size
