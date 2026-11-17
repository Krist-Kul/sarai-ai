"""Transcript -> meeting type and speaker names, before the minutes are written.

The upload form asks for a title, a time and, optionally, who was there.
Everything else is read off the transcript here, in one LLM call:

- the meeting type, which shapes the summarizer's emphasis (meeting_types.py);
- a name for each diarized speaker, so the minutes say "คุณสมชาย" rather
  than "SPEAKER_03".

Names follow the same evidence rule as action items in summarize.py: every
name must come with a verbatim quote from the transcript that supports it,
and the quote must actually be in the transcript and either contain the name
or tie the speaker to someone the organizer listed. A wrong name is worse
than no name: it puts words in a real person's mouth. A speaker nobody can
name gets a neutral numbered label instead.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field, ValidationError

from sarai import thai
from sarai.config import Settings
from sarai.llm import prompt
from sarai.llm.client import Chat, LLMError, get_chat
from sarai.models import MeetingType, Segment, SummarizeInput

log = logging.getLogger("sarai.llm")

# Turns of context kept around a speaker's first appearance when a long
# transcript has to be cut down to fit the call.
_CONTEXT_TURNS = 3
# Turns kept per speaker who first speaks after the opening excerpt.
_TURNS_PER_LATE_SPEAKER = 4

_WS = re.compile(r"\s+")
_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)

# Stripped before checking that a quote mentions a name: people are addressed
# as "คุณสมชาย" and listed as "สมชาย", or the other way round.
_HONORIFICS = re.compile(
    r"^(คุณ|นาย|นางสาว|นาง|ดร\.?|ท่าน|พี่|น้อง|อาจารย์|ศ\.|รศ\.|ผศ\.|"
    r"mr\.?|mrs\.?|ms\.?|miss|dr\.?|prof\.?)\s*",
    re.IGNORECASE,
)

FALLBACK_LABEL = "ผู้พูด {n}"

_SYSTEM = """\
You read a diarized transcript of a real meeting (Thai, English, or both) and
report two things about it. OUTPUT: valid JSON only, no markdown fences.

Schema:
{
  "meeting_type": one of {types},
  "speakers": [
    {"label": string, "name": string, "evidence": string}
  ]
}

MEETING TYPE — pick the one that fits best:
{type_guide}

SPEAKERS — for each speaker label (SPEAKER_00, SPEAKER_01, ...) you can
identify, give the person's name as it should appear in the minutes.

1. NEVER GUESS. Only name a speaker when the transcript shows who they are:
   they introduce themselves ("ผมชื่อสมชาย", "I'm Jane from finance"), someone
   hands them the floor by name right before they speak ("เชิญคุณสมชายครับ"),
   or they answer to their name. Speaking a lot, or talking about a topic, is
   not evidence.
2. "evidence" is a short VERBATIM snippet copied from the transcript that
   proves the name. It must contain the name, unless it ties the speaker to
   someone in the organizer's attendee list by a role they state.
3. When the organizer listed attendees, use their spelling of the name.
4. A role is acceptable as the name only when it is stated and nobody's real
   name is known ("ประธานที่ประชุม", "the interviewer").
5. Leave a speaker out entirely rather than guess. Two labels must not get the
   same name unless the transcript shows they are the same person.
"""

_TYPE_GUIDE = {
    MeetingType.GENERAL: "anything that fits none of the others",
    MeetingType.EXECUTIVE: "management or board meeting: decisions, owners, formal agenda",
    MeetingType.STANDUP: "team stand-up or status sync: each person reports progress/blockers",
    MeetingType.LECTURE: "lecture, seminar, class or presentation: one main speaker teaching",
    MeetingType.INTERVIEW: "interview: one side asks questions, the other answers",
    MeetingType.WORKSHOP: "workshop or brainstorming: a group generating ideas",
}


class SpeakerName(BaseModel):
    label: str
    name: str
    evidence: str = ""


class Analysis(BaseModel):
    meeting_type: MeetingType = MeetingType.GENERAL
    speakers: list[SpeakerName] = Field(default_factory=list)


def system_prompt() -> str:
    types = ", ".join(f'"{t.value}"' for t in MeetingType)
    guide = "\n".join(f"- {t.value}: {desc}" for t, desc in _TYPE_GUIDE.items())
    return _SYSTEM.replace("{types}", types).replace("{type_guide}", guide)


def excerpt(segments: list[Segment], max_chars: int) -> list[Segment]:
    """The segments the analysis call sees.

    Short meetings go in whole. A long one is cut to its opening -- where
    introductions and the agenda live -- plus the first few turns of every
    speaker who only joins later, with the turns just before them, which is
    where they get handed the floor by name.
    """
    if sum(len(s.text) for s in segments) <= max_chars:
        return segments

    keep: set[int] = set()
    used = 0
    for i, seg in enumerate(segments):
        if used + len(seg.text) > max_chars and keep:
            break
        keep.add(i)
        used += len(seg.text)

    seen = {segments[i].speaker for i in keep}
    for i, seg in enumerate(segments):
        if seg.speaker in seen:
            continue
        seen.add(seg.speaker)
        keep.update(range(max(0, i - _CONTEXT_TURNS), i))
        own = [j for j in range(i, len(segments)) if segments[j].speaker == seg.speaker]
        keep.update(own[:_TURNS_PER_LATE_SPEAKER])
    return [segments[i] for i in sorted(keep)]


def build_user_message(inp: SummarizeInput, segments: list[Segment]) -> str:
    parts: list[str] = []
    if inp.title:
        parts.append(f"Meeting title: {inp.title}")
    if inp.attendees:
        listed = ", ".join(a.name if not a.role else f"{a.name} ({a.role})" for a in inp.attendees)
        parts.append(f"Attendees listed by the organizer: {listed}")
    labels = sorted({s.speaker for s in inp.segments})
    parts.append(f"Speaker labels to identify: {', '.join(labels)}")
    parts.append("Transcript (may skip parts of a long meeting):")
    # Raw labels: the model is naming them, so it must see the keys.
    parts.append(prompt.transcript_lines(segments, {}))
    return "\n".join(parts)


def _squash(text: str) -> str:
    return _WS.sub("", thai.normalize(text)).lower()


def _core(name: str) -> str:
    return _squash(_HONORIFICS.sub("", name.strip()))


def verify(analysis: Analysis, inp: SummarizeInput) -> dict[str, str]:
    """Names that pass the evidence rule, keyed by speaker label."""
    haystack = _squash(" ".join(s.text for s in inp.segments))
    known_labels = {s.speaker for s in inp.segments}
    listed = {_core(a.name) for a in inp.attendees if a.name.strip()}

    out: dict[str, str] = {}
    for item in analysis.speakers:
        name = item.name.strip()
        quote = _squash(item.evidence)
        if item.label not in known_labels or not name or not quote:
            continue
        if quote not in haystack:
            log.info("dropping speaker name %r: evidence not in transcript", name)
            continue
        core = _core(name)
        if core and core not in quote and core not in listed:
            log.info("dropping speaker name %r: evidence does not mention it", name)
            continue
        out[item.label] = name

    # One name, two labels: the model could not tell them apart, so neither is
    # safe. Diarization splitting one person in two is handled by the editor.
    by_name: dict[str, list[str]] = {}
    for label, name in out.items():
        by_name.setdefault(_core(name), []).append(label)
    for labels in by_name.values():
        if len(labels) > 1:
            for label in labels:
                out.pop(label)
    return out


def fallback_labels(labels: list[str]) -> dict[str, str]:
    """Neutral, stable names for speakers nobody could identify."""
    return {label: FALLBACK_LABEL.format(n=i) for i, label in enumerate(sorted(labels), start=1)}


def _parse(raw: str) -> Analysis:
    match = _FENCE.match(raw)
    return Analysis.model_validate_json(match.group(1) if match else raw.strip())


async def analyze(
    inp: SummarizeInput, settings: Settings, *, chat: Chat | None = None
) -> tuple[MeetingType, dict[str, str]]:
    """Returns (meeting type, {speaker label: verified name})."""
    if not inp.segments:
        raise LLMError("This meeting has no transcript to analyze")
    client = chat if chat is not None else get_chat(settings)
    system = system_prompt()
    user = build_user_message(inp, excerpt(inp.segments, settings.llm_chunk_chars))
    raw = await client.complete(system, user)
    try:
        analysis = _parse(raw)
    except ValidationError as first:
        log.warning("model returned invalid analysis JSON; retrying with the error")
        try:
            analysis = _parse(await client.complete(system, prompt.retry_message(user, str(first))))
        except ValidationError as second:
            raise LLMError(f"The model could not identify the meeting: {second}") from second
    return analysis.meeting_type, verify(analysis, inp)
