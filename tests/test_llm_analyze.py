"""Meeting type detection and speaker naming: the evidence rule, without a network call."""

from __future__ import annotations

import asyncio
import json

import pytest

from sarai.config import get_settings
from sarai.llm.analyze import Analysis, SpeakerName, analyze, excerpt, fallback_labels, verify
from sarai.models import Attendee, MeetingType, Segment, SummarizeInput

SEGMENTS = [
    Segment(id=0, start=0, end=4, speaker="SPEAKER_00", text="สวัสดีครับ ผมสมชาย เป็นประธานวันนี้"),
    Segment(id=1, start=4, end=8, speaker="SPEAKER_00", text="เชิญคุณมาลีรายงานยอดขายครับ"),
    Segment(id=2, start=8, end=12, speaker="SPEAKER_01", text="ค่ะ ยอดขายเดือนนี้ดีขึ้น"),
    Segment(id=3, start=12, end=16, speaker="SPEAKER_02", text="ผมดูแลฝ่ายบัญชีครับ"),
]


def _inp(attendees: list[Attendee] | None = None) -> SummarizeInput:
    return SummarizeInput(title="ประชุม", segments=SEGMENTS, attendees=attendees or [])


def test_names_with_verbatim_evidence_are_kept() -> None:
    analysis = Analysis(
        speakers=[
            SpeakerName(label="SPEAKER_00", name="สมชาย", evidence="ผมสมชาย เป็นประธาน"),
            SpeakerName(label="SPEAKER_01", name="คุณมาลี", evidence="เชิญคุณมาลีรายงาน"),
        ]
    )
    assert verify(analysis, _inp()) == {"SPEAKER_00": "สมชาย", "SPEAKER_01": "คุณมาลี"}


def test_an_invented_quote_drops_the_name() -> None:
    analysis = Analysis(
        speakers=[SpeakerName(label="SPEAKER_01", name="มาลี", evidence="ดิฉันชื่อมาลีค่ะ")]
    )
    assert verify(analysis, _inp()) == {}


def test_a_real_quote_that_never_mentions_the_name_drops_it() -> None:
    """Speaking about sales is not evidence of being called Malee."""
    analysis = Analysis(
        speakers=[SpeakerName(label="SPEAKER_01", name="มาลี", evidence="ยอดขายเดือนนี้ดีขึ้น")]
    )
    assert verify(analysis, _inp()) == {}


def test_a_role_quote_can_name_someone_the_organizer_listed() -> None:
    analysis = Analysis(
        speakers=[SpeakerName(label="SPEAKER_02", name="วิชัย", evidence="ผมดูแลฝ่ายบัญชีครับ")]
    )
    listed = _inp([Attendee(name="คุณวิชัย", role="ฝ่ายบัญชี")])
    assert verify(analysis, listed) == {"SPEAKER_02": "วิชัย"}
    assert verify(analysis, _inp()) == {}


def test_one_name_on_two_labels_is_dropped_from_both() -> None:
    analysis = Analysis(
        speakers=[
            SpeakerName(label="SPEAKER_00", name="สมชาย", evidence="ผมสมชาย"),
            SpeakerName(label="SPEAKER_02", name="คุณสมชาย", evidence="ผมสมชาย"),
        ]
    )
    assert verify(analysis, _inp()) == {}


def test_unknown_labels_are_ignored() -> None:
    analysis = Analysis(
        speakers=[SpeakerName(label="SPEAKER_09", name="สมชาย", evidence="ผมสมชาย")]
    )
    assert verify(analysis, _inp()) == {}


def test_fallback_labels_are_numbered_in_label_order() -> None:
    assert fallback_labels(["SPEAKER_01", "SPEAKER_00"]) == {
        "SPEAKER_00": "ผู้พูด 1",
        "SPEAKER_01": "ผู้พูด 2",
    }


def test_excerpt_keeps_a_speaker_who_only_joins_late() -> None:
    long = [
        Segment(id=i, start=i, end=i + 1, speaker="SPEAKER_00", text="ก" * 100) for i in range(50)
    ]
    late = Segment(id=50, start=50, end=51, speaker="SPEAKER_01", text="ผมวิชัยครับ")
    cut = excerpt([*long, late], max_chars=1_000)
    assert sum(len(s.text) for s in cut) < sum(len(s.text) for s in long)
    assert late in cut
    # The turns just before the late speaker are where they get introduced.
    assert long[-1] in cut


class StubChat:
    model = "stub"

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls = 0

    async def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return self.replies.pop(0)


def test_analyze_returns_the_type_and_verified_names() -> None:
    reply = json.dumps(
        {
            "meeting_type": "executive",
            "speakers": [
                {"label": "SPEAKER_00", "name": "สมชาย", "evidence": "ผมสมชาย"},
                {"label": "SPEAKER_01", "name": "นิดา", "evidence": "ชื่อนิดา"},
            ],
        },
        ensure_ascii=False,
    )
    meeting_type, names = asyncio.run(analyze(_inp(), get_settings(), chat=StubChat(reply)))
    assert meeting_type is MeetingType.EXECUTIVE
    assert names == {"SPEAKER_00": "สมชาย"}


def test_analyze_retries_once_on_invalid_json() -> None:
    good = json.dumps({"meeting_type": "lecture", "speakers": []})
    chat = StubChat('{"meeting_type": "party"}', good)
    meeting_type, _ = asyncio.run(analyze(_inp(), get_settings(), chat=chat))
    assert meeting_type is MeetingType.LECTURE
    assert chat.calls == 2


def test_analyze_without_a_transcript_is_an_error() -> None:
    from sarai.llm.client import LLMError

    with pytest.raises(LLMError):
        asyncio.run(analyze(SummarizeInput(), get_settings(), chat=StubChat("{}")))
