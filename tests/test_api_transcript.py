"""Transcript review endpoints."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from sarai import db
from sarai.api.main import create_app
from sarai.models import Meeting, Segment


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def meeting_id() -> str:
    """A meeting with a two-speaker transcript already saved."""
    mid = "m1"
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
        db.save_transcript(
            conn,
            mid,
            [
                Segment(id=0, start=0, end=5, speaker="SPEAKER_00", text="สวัสดีครับ"),
                Segment(id=1, start=5, end=9, speaker="SPEAKER_01", text="สวัสดีค่ะ"),
            ],
            edited=False,
        )
        db.save_speakers(conn, mid, {"SPEAKER_00": "SPEAKER_00", "SPEAKER_01": "SPEAKER_01"})
    return mid


def test_get_transcript_returns_segments_and_speakers(client: TestClient, meeting_id: str) -> None:
    body = client.get(f"/api/meetings/{meeting_id}/transcript").json()
    assert [s["text"] for s in body["segments"]] == ["สวัสดีครับ", "สวัสดีค่ะ"]
    assert body["speakers"]["SPEAKER_00"] == "SPEAKER_00"
    assert body["edited"] is False


def test_get_transcript_404s_before_transcription(client: TestClient) -> None:
    with db.connection() as conn:
        db.create_meeting(
            conn,
            Meeting(
                id="empty",
                title="t",
                source_file="a.mp3",
                audio_path="/tmp/a.wav",
                created_at=db.utcnow(),
            ),
        )
    assert client.get("/api/meetings/empty/transcript").status_code == 404


def test_editing_a_segment_persists_and_marks_the_transcript_edited(
    client: TestClient, meeting_id: str
) -> None:
    current = client.get(f"/api/meetings/{meeting_id}/transcript").json()
    current["segments"][0]["text"] = "สวัสดีครับ ผมขอเริ่มเลย"

    resp = client.patch(
        f"/api/meetings/{meeting_id}/transcript", json={"segments": current["segments"]}
    )
    assert resp.status_code == 200, resp.text

    reloaded = client.get(f"/api/meetings/{meeting_id}/transcript").json()
    assert reloaded["segments"][0]["text"] == "สวัสดีครับ ผมขอเริ่มเลย"
    assert reloaded["edited"] is True


def test_transcript_cannot_be_saved_empty_or_with_duplicate_ids(
    client: TestClient, meeting_id: str
) -> None:
    assert (
        client.patch(f"/api/meetings/{meeting_id}/transcript", json={"segments": []}).status_code
        == 422
    )

    seg = {"id": 0, "start": 0, "end": 1, "speaker": "SPEAKER_00", "text": "a"}
    resp = client.patch(
        f"/api/meetings/{meeting_id}/transcript", json={"segments": [seg, dict(seg)]}
    )
    assert resp.status_code == 422


def test_renaming_a_speaker_applies_everywhere(client: TestClient, meeting_id: str) -> None:
    resp = client.patch(
        f"/api/meetings/{meeting_id}/speakers",
        json={"speakers": {"SPEAKER_00": "คุณสมชาย"}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["SPEAKER_00"] == "คุณสมชาย"

    body = client.get(f"/api/meetings/{meeting_id}/transcript").json()
    assert body["speakers"] == {"SPEAKER_00": "คุณสมชาย", "SPEAKER_01": "SPEAKER_01"}


def test_blank_label_resets_a_speaker_to_its_raw_key(client: TestClient, meeting_id: str) -> None:
    client.patch(
        f"/api/meetings/{meeting_id}/speakers", json={"speakers": {"SPEAKER_00": "คุณสมชาย"}}
    )
    resp = client.patch(
        f"/api/meetings/{meeting_id}/speakers", json={"speakers": {"SPEAKER_00": "   "}}
    )
    assert resp.json()["SPEAKER_00"] == "SPEAKER_00"


def test_renaming_an_unknown_speaker_is_rejected(client: TestClient, meeting_id: str) -> None:
    resp = client.patch(
        f"/api/meetings/{meeting_id}/speakers", json={"speakers": {"SPEAKER_99": "ผี"}}
    )
    assert resp.status_code == 422
    assert "SPEAKER_99" in resp.json()["detail"]
