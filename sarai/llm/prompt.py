"""Prompts for the summarizer.

The system prompt is the contract with the model. The rules are kept verbatim
from the spec: every one exists because the failure it prevents was observed --
invented owners, translated Thai, action items with no evidence. Only the
persona, the summary guidance and a type-specific focus rule vary with the
meeting type (see sarai/meeting_types.py); the rules never do.
"""

from __future__ import annotations

from sarai import thai
from sarai.meeting_types import profile
from sarai.models import MeetingType, MinutesContent, MinutesJSON, Segment, SummarizeInput

_SYSTEM_TEMPLATE = """\
{persona} You receive a diarized transcript of a real meeting.

OUTPUT: valid JSON only. No markdown fences, no preamble, no explanation.

Schema:
{
  "title": string,
  "meeting_date": string | null,
  "attendees": [{"name": string, "role": string | null}],
  "summary": string,                 // {summary_guidance}
  "agenda": [string],
  "discussion": [
    {"topic": string, "points": [string], "speakers": [string]}
  ],
  "decisions": [{"decision": string, "rationale": string | null}],
  "action_items": [
    {"task": string, "owner": string | null, "due": string | null,
     "source_quote": string}
  ],
  "open_questions": [string],
  "next_meeting": string | null
}

RULES — follow these strictly:

1. LANGUAGE: Write each field in the language that dominated that part of the
   discussion. Do NOT translate. If the meeting was conducted in Thai with
   English technical terms mixed in, preserve that mixture exactly as spoken.
   A Thai reader must recognize their own meeting.

2. NEVER INVENT. If no owner was named for an action item, use null. If no
   deadline was stated, use null. Do not guess. Do not infer an owner from
   who happened to be speaking.

3. EVIDENCE: every action_item must include "source_quote" — a short verbatim
   snippet from the transcript that justifies it. If you cannot find one, the
   action item does not belong in the list.

4. DECISIONS vs DISCUSSION: a decision is something the group concluded or
   committed to. "We should probably look into X" is discussion. "OK let's go
   with X, ตกลงตามนี้" is a decision. Be conservative.

5. NAMES: use the speaker labels provided. Correct obvious ASR misspellings of
   names and terms using the glossary provided. Do not correct anything else.

6. NOISE: ignore small talk, greetings, connection problems, and side
   conversations that carry no decision or information.

7. NUMBERS: normalize spoken numbers to digits in decisions and action items
   ("สองพันห้า" -> 2,500). A wrong figure there has consequences.

8. MEETING TYPE: {focus}
   Leave a list empty rather than pad it; rules 2-4 still apply.
"""


def system_prompt(meeting_type: MeetingType = MeetingType.GENERAL) -> str:
    p = profile(meeting_type)
    # str.replace, not str.format: the template is full of JSON braces.
    return (
        _SYSTEM_TEMPLATE.replace("{persona}", p.persona)
        .replace("{summary_guidance}", p.summary_guidance)
        .replace("{focus}", p.focus)
    )


# The original executive-minutes prompt, kept as a name for callers and tests.
SYSTEM_PROMPT = system_prompt(MeetingType.EXECUTIVE)

_REDUCE_TEMPLATE = """\
You are merging partial meeting minutes produced from consecutive chunks of one
meeting transcript. They overlap slightly, so the same decision may appear more
than once.

OUTPUT: valid JSON only, in the same schema as the parts. No markdown fences.

RULES:
1. Deduplicate decisions and open questions that say the same thing; keep the
   fuller wording.
2. Consolidate action items by owner and task. Keep the source_quote of the one
   you keep — never merge two quotes into one, and never write a new quote.
3. Preserve the language of each part exactly. Do not translate.
4. Merge discussion topics that cover the same subject; keep every distinct
   point.
5. Never introduce a fact that is not in one of the parts.
6. The summary field is rewritten as one overview of the whole meeting:
   {summary_guidance}.
"""


def reduce_prompt(meeting_type: MeetingType = MeetingType.GENERAL) -> str:
    return _REDUCE_TEMPLATE.replace("{summary_guidance}", profile(meeting_type).summary_guidance)


TRANSLATE_PROMPT = """\
You translate finished meeting minutes into English for readers who do not
read Thai. You receive the minutes as JSON.

OUTPUT: valid JSON only, in exactly the same schema. No markdown fences.

RULES:
1. Translate every text value into natural, professional English. Text that is
   already English stays as it is.
2. Keep the structure: the same keys, the same lists in the same order, the
   same number of items in each list.
3. Keep "source_quote" verbatim, untranslated: it is evidence of what was said.
4. Write people's names in English letters (คุณสมชาย -> Khun Somchai). Keep
   figures, dates and times exactly as given; null stays null.
5. Add nothing and leave nothing out. This is a translation, not a rewrite.
"""


def build_translate_message(minutes: MinutesContent) -> str:
    content = MinutesContent.model_validate(minutes.model_dump())
    return f"Translate these minutes:\n\n{content.model_dump_json(indent=None)}"


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def transcript_lines(segments: list[Segment], speakers: dict[str, str]) -> str:
    """`[HH:MM:SS] Label: text`, one line per segment, in chronological order."""
    lines = []
    for seg in segments:
        label = speakers.get(seg.speaker) or seg.speaker
        text = thai.normalize(seg.text)
        lines.append(f"[{format_timestamp(seg.start)}] {label}: {text}")
    return "\n".join(lines)


def build_user_message(inp: SummarizeInput, segments: list[Segment] | None = None) -> str:
    """Context block, then the transcript. Everything the model is allowed to use."""
    body = segments if segments is not None else inp.segments
    parts: list[str] = []
    if inp.title:
        parts.append(f"Meeting title: {inp.title}")
    if inp.meeting_date:
        parts.append(f"Meeting date: {inp.meeting_date}")
    if inp.attendees:
        listed = ", ".join(a.name if not a.role else f"{a.name} ({a.role})" for a in inp.attendees)
        parts.append(f"Attendees given by the organizer: {listed}")
    if inp.glossary:
        parts.append(
            "Glossary — these are the correct spellings of project names, "
            f"people and acronyms used in this meeting: {', '.join(inp.glossary)}"
        )
    if inp.speakers:
        mapping = ", ".join(f"{key} = {label}" for key, label in sorted(inp.speakers.items()))
        parts.append(f"Speaker labels: {mapping}")
    parts.append("Transcript:")
    parts.append(transcript_lines(body, inp.speakers))
    return "\n".join(parts)


def build_reduce_message(parts: list[MinutesJSON]) -> str:
    numbered = "\n\n".join(
        f"PART {i + 1}:\n{p.model_dump_json(indent=None)}" for i, p in enumerate(parts)
    )
    return f"Here are {len(parts)} partial minutes from one meeting.\n\n{numbered}"


def retry_message(original: str, error: str) -> str:
    """Second attempt after a schema violation: show the model its own error."""
    return (
        f"{original}\n\n"
        "Your previous response did not validate against the schema. "
        f"The validator reported:\n{error}\n"
        "Return corrected JSON only."
    )
