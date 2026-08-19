"""Transcript -> MinutesJSON.

Three things happen here and nowhere else:

1. Long meetings are split at segment boundaries and reduced back together.
2. Every response is validated against MinutesJSON, with one retry that shows
   the model its own validation error -- models correct schema violations
   reliably when told what was wrong, and not at all when they are not.
3. Action items whose `source_quote` is not actually in the transcript are
   dropped. An invented quote means an invented commitment, and a meeting
   participant assigned work they never agreed to is the worst failure this
   system can produce.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable

from pydantic import ValidationError

from sarai import thai
from sarai.config import Settings
from sarai.llm import chunk, prompt
from sarai.llm.client import Chat, LLMError, get_chat
from sarai.models import MinutesJSON, Segment, SummarizeInput

log = logging.getLogger("sarai.llm")

Progress = Callable[[float, str], None]

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)

# Quotes are compared with whitespace collapsed: the transcript keeps the
# spacing the ASR produced, and a model that retypes a quote almost always
# normalizes it. Thai has no word spaces, so this cannot split words.
_WS = re.compile(r"\s+")


def _strip_fence(text: str) -> str:
    """The prompt forbids markdown fences. Models add them anyway."""
    match = _FENCE.match(text)
    return match.group(1) if match else text.strip()


def _normalize(text: str) -> str:
    return _WS.sub("", text)


def verify_quotes(minutes: MinutesJSON, segments: list[Segment]) -> tuple[MinutesJSON, int]:
    """Drop action items whose source_quote is not in the transcript.

    Returns the filtered minutes and how many were dropped, so the caller can
    tell the user rather than silently shrinking their list.
    """
    haystack = _normalize(" ".join(thai.normalize(s.text) for s in segments))
    kept = []
    dropped = 0
    for item in minutes.action_items:
        needle = _normalize(item.source_quote)
        if needle and needle in haystack:
            kept.append(item)
        else:
            dropped += 1
            log.info("dropping action item with unverifiable quote: %r", item.source_quote[:80])
    if dropped:
        minutes = minutes.model_copy(update={"action_items": kept})
    return minutes, dropped


async def _call_validated(chat: Chat, system: str, user: str) -> MinutesJSON:
    """One call, one retry showing the model its validation error, then fail."""
    raw = _strip_fence(await chat.complete(system, user))
    try:
        return MinutesJSON.model_validate_json(raw)
    except ValidationError as first:
        log.warning("model returned invalid minutes JSON; retrying with the error")
        retry = await chat.complete(system, prompt.retry_message(user, str(first)))
        try:
            return MinutesJSON.model_validate_json(_strip_fence(retry))
        except ValidationError as second:
            raise LLMError(
                "The model returned minutes that do not match the required schema, "
                f"twice. Last error: {second.errors()[0].get('msg', second)}"
            ) from second


async def summarize(
    inp: SummarizeInput,
    settings: Settings,
    *,
    chat: Chat | None = None,
    on_progress: Progress | None = None,
) -> tuple[MinutesJSON, str, int]:
    """Returns (minutes, model name, dropped action items).

    `chat` is injectable so tests can run the whole map-reduce and validation
    path without a network call.
    """
    if not inp.segments:
        raise LLMError("This meeting has no transcript to summarize")

    client = chat if chat is not None else get_chat(settings)
    total = chunk.total_chars(inp.segments)

    if total <= settings.llm_single_call_chars:
        if on_progress:
            on_progress(0.3, f"summarizing {len(inp.segments)} segments")
        minutes = await _call_validated(
            client, prompt.SYSTEM_PROMPT, prompt.build_user_message(inp)
        )
    else:
        chunks = chunk.split_segments(
            inp.segments,
            max_chars=settings.llm_chunk_chars,
            overlap=settings.llm_chunk_overlap_segments,
        )
        log.info("map-reduce: %d chars over %d chunk(s)", total, len(chunks))
        parts: list[MinutesJSON] = []
        for index, part in enumerate(chunks, start=1):
            if on_progress:
                # Reserve the last fifth of the stage for the reduce call.
                on_progress(0.8 * index / len(chunks), f"part {index} of {len(chunks)}")
            parts.append(
                await _call_validated(
                    client, prompt.SYSTEM_PROMPT, prompt.build_user_message(inp, part)
                )
            )
        if on_progress:
            on_progress(0.85, f"merging {len(parts)} parts")
        minutes = await _call_validated(
            client, prompt.REDUCE_PROMPT, prompt.build_reduce_message(parts)
        )

    # The model is told to use the meeting's own title and date; if it invented
    # one anyway, the meeting record wins.
    if inp.title:
        minutes = minutes.model_copy(update={"title": inp.title})
    if inp.meeting_date and not minutes.meeting_date:
        minutes = minutes.model_copy(update={"meeting_date": inp.meeting_date})

    minutes, dropped = verify_quotes(minutes, inp.segments)
    return minutes, client.model, dropped


def minutes_to_json(minutes: MinutesJSON) -> str:
    return json.dumps(minutes.model_dump(), ensure_ascii=False, indent=2)
