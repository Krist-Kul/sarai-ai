"""Chunker, validation retry, and quote verification.

No network: a fake Chat records what it was asked and returns canned JSON, so
the whole map-reduce path is exercised deterministically.
"""

from __future__ import annotations

import json

import pytest

import sarai.llm.summarize as summarize_mod
from sarai import meeting_types
from sarai.config import get_settings
from sarai.llm import chunk, prompt
from sarai.llm.client import LLMError
from sarai.models import MeetingType, MinutesJSON, Segment, SummarizeInput


def seg(index: int, text: str, speaker: str = "SPEAKER_00") -> Segment:
    return Segment(id=index, start=index * 10.0, end=index * 10.0 + 9, speaker=speaker, text=text)


class FakeChat:
    """Returns each queued response in turn and remembers every prompt."""

    model = "fake-model"

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    async def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if not self.responses and system == prompt.TRANSLATE_PROMPT:
            # A test that queued nothing for the translation gets the minutes back.
            return user.split("\n\n", 1)[1]
        if not self.responses:
            raise AssertionError("FakeChat ran out of responses")
        return self.responses.pop(0)


def minutes_json(**overrides: object) -> str:
    payload: dict[str, object] = {
        "title": "ประชุมทีม",
        "meeting_date": "2026-08-14",
        "summary": "สรุปการประชุม",
        "action_items": [],
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------


def test_chunks_split_at_segment_boundaries_with_overlap() -> None:
    segments = [seg(i, "ก" * 100) for i in range(10)]
    chunks = chunk.split_segments(segments, max_chars=250, overlap=2)

    assert len(chunks) > 1
    for part in chunks:
        # Every chunk is whole segments -- no segment appears cut in half.
        assert all(s in segments for s in part)
    # Consecutive chunks share their boundary segments.
    assert chunks[0][-2:] == chunks[1][:2]


def test_oversized_segment_is_never_cut() -> None:
    segments = [seg(0, "ก" * 500), seg(1, "ข" * 10)]
    chunks = chunk.split_segments(segments, max_chars=100, overlap=0)
    assert segments[0] in chunks[0]
    assert len(chunks[0][0].text) == 500


def test_empty_transcript_produces_no_chunks() -> None:
    assert chunk.split_segments([], max_chars=100) == []


# --------------------------------------------------------------------------
# Quote verification
# --------------------------------------------------------------------------


def test_action_items_with_invented_quotes_are_dropped() -> None:
    segments = [seg(0, "เดี๋ยวจะส่งเอกสารให้ภายในวันศุกร์")]
    minutes = MinutesJSON.model_validate(
        {
            "title": "t",
            "action_items": [
                {"task": "ส่งเอกสาร", "source_quote": "จะส่งเอกสารให้ภายในวันศุกร์"},
                {"task": "ยกเลิกสัญญา", "source_quote": "ผมจะยกเลิกสัญญาทั้งหมด"},
            ],
        }
    )
    filtered, dropped = summarize_mod.verify_quotes(minutes, segments)
    assert dropped == 1
    assert [i.task for i in filtered.action_items] == ["ส่งเอกสาร"]


def test_quote_matching_ignores_whitespace_differences() -> None:
    segments = [seg(0, "เดี๋ยว จะส่ง ให้วันศุกร์")]
    minutes = MinutesJSON.model_validate(
        {"title": "t", "action_items": [{"task": "ส่ง", "source_quote": "เดี๋ยวจะส่งให้วันศุกร์"}]}
    )
    _, dropped = summarize_mod.verify_quotes(minutes, segments)
    assert dropped == 0


# --------------------------------------------------------------------------
# The summarize path
# --------------------------------------------------------------------------


async def test_short_meeting_uses_a_single_call() -> None:
    settings = get_settings()
    chat = FakeChat([minutes_json(), minutes_json(title="Team meeting")])
    inp = SummarizeInput(title="ประชุมทีม", segments=[seg(0, "สวัสดีครับ")])

    minutes, model, dropped = await summarize_mod.summarize(inp, settings, chat=chat)

    # The minutes, then their English translation.
    assert len(chat.calls) == 2
    assert chat.calls[1][0] == prompt.TRANSLATE_PROMPT
    assert minutes.english is not None and minutes.english.title == "Team meeting"
    assert model == "fake-model"
    assert dropped == 0
    assert minutes.title == "ประชุมทีม"


async def test_long_meeting_maps_then_reduces() -> None:
    settings = get_settings().model_copy(
        update={"llm_single_call_chars": 300, "llm_chunk_chars": 150}
    )
    segments = [seg(i, "ก" * 100) for i in range(6)]
    chat = FakeChat([minutes_json() for _ in range(10)])

    await summarize_mod.summarize(SummarizeInput(segments=segments), settings, chat=chat)

    # One call per chunk, the reduce call, then the translation.
    assert len(chat.calls) >= 4
    assert chat.calls[-2][0].startswith("You are merging partial meeting minutes")


async def test_invalid_json_is_retried_once_with_the_validation_error() -> None:
    settings = get_settings()
    chat = FakeChat(['{"meeting_date": "2026-08-14"}', minutes_json()])

    minutes, _, _ = await summarize_mod.summarize(
        SummarizeInput(segments=[seg(0, "สวัสดี")]), settings, chat=chat
    )

    assert len(chat.calls) == 3  # first try, retry, translation
    # The retry shows the model what the validator complained about.
    assert "did not validate" in chat.calls[1][1]
    assert minutes.summary == "สรุปการประชุม"


async def test_two_invalid_responses_fail_with_a_readable_message() -> None:
    settings = get_settings()
    chat = FakeChat(["not json at all", '{"still": "wrong"}'])

    with pytest.raises(LLMError, match="do not match the required schema"):
        await summarize_mod.summarize(
            SummarizeInput(segments=[seg(0, "สวัสดี")]), settings, chat=chat
        )


async def test_markdown_fences_are_tolerated() -> None:
    settings = get_settings()
    chat = FakeChat([f"```json\n{minutes_json()}\n```"])

    minutes, _, _ = await summarize_mod.summarize(
        SummarizeInput(segments=[seg(0, "สวัสดี")]), settings, chat=chat
    )
    assert minutes.summary == "สรุปการประชุม"


async def test_empty_transcript_is_refused_before_any_call() -> None:
    chat = FakeChat([])
    with pytest.raises(LLMError, match="no transcript"):
        await summarize_mod.summarize(SummarizeInput(segments=[]), get_settings(), chat=chat)
    assert chat.calls == []


async def test_prompt_carries_speaker_labels_and_glossary() -> None:
    settings = get_settings()
    chat = FakeChat([minutes_json()])
    inp = SummarizeInput(
        glossary=["deploy", "PDPA"],
        speakers={"SPEAKER_00": "คุณสมชาย"},
        segments=[seg(0, "ขอเริ่มที่เรื่อง deploy")],
    )

    await summarize_mod.summarize(inp, settings, chat=chat)

    _, user = chat.calls[0]
    assert "deploy, PDPA" in user
    assert "SPEAKER_00 = คุณสมชาย" in user
    # Segments are rendered as [HH:MM:SS] Label: text, using the label.
    assert "[00:00:00] คุณสมชาย: ขอเริ่มที่เรื่อง deploy" in user


@pytest.mark.parametrize("meeting_type", list(MeetingType))
def test_every_meeting_type_keeps_the_evidence_rules(meeting_type: MeetingType) -> None:
    system = prompt.system_prompt(meeting_type)
    profile = meeting_types.profile(meeting_type)

    assert system.startswith(profile.persona)
    assert profile.summary_guidance in system
    assert profile.focus in system
    # The rules that stop invented owners and quotes are not negotiable per type.
    for rule in ("NEVER INVENT", "source_quote", "DECISIONS vs DISCUSSION", "Do NOT translate"):
        assert rule in system
    # Placeholders all filled, JSON schema braces untouched.
    assert "{persona}" not in system and "{focus}" not in system
    assert '"attendees": [{"name": string' in system


def test_executive_prompt_is_the_original_one() -> None:
    assert prompt.system_prompt(MeetingType.EXECUTIVE) == prompt.SYSTEM_PROMPT
    assert "executive overview" in prompt.SYSTEM_PROMPT
    assert "executive overview" not in prompt.system_prompt(MeetingType.LECTURE)


async def test_meeting_type_reaches_map_and_reduce_prompts() -> None:
    settings = get_settings().model_copy(
        update={"llm_single_call_chars": 300, "llm_chunk_chars": 150}
    )
    segments = [seg(i, "ก" * 60) for i in range(8)]
    # One response per map call plus the reduce; extras are never consumed.
    chat = FakeChat([minutes_json()] * (len(segments) + 2))
    inp = SummarizeInput(meeting_type=MeetingType.LECTURE, segments=segments)

    await summarize_mod.summarize(inp, settings, chat=chat)

    lecture = meeting_types.profile(MeetingType.LECTURE)
    systems = [system for system, _ in chat.calls]
    assert len(systems) > 2  # really went through map-reduce
    assert systems[-1] == prompt.TRANSLATE_PROMPT
    systems = systems[:-1]
    assert all(lecture.summary_guidance in s for s in systems)
    assert systems[-1] == prompt.reduce_prompt(MeetingType.LECTURE)


async def test_translation_keeps_the_original_quotes() -> None:
    minutes = MinutesJSON.model_validate(
        {"title": "t", "action_items": [{"task": "ส่ง", "source_quote": "จะส่งให้"}]}
    )
    english = minutes_json(
        title="t", action_items=[{"task": "Send", "source_quote": "will send it"}]
    )
    out = await summarize_mod.translate(FakeChat([english]), minutes)
    assert out.english is not None
    assert out.english.action_items[0].task == "Send"
    assert out.english.action_items[0].source_quote == "จะส่งให้"


async def test_failed_translation_keeps_the_thai_minutes() -> None:
    minutes = MinutesJSON(title="t", summary="สรุป")
    out = await summarize_mod.translate(FakeChat(["not json", "still not json"]), minutes)
    assert out.english is None
    assert out.summary == "สรุป"
