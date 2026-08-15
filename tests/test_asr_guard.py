"""Hallucination guard.

Whisper-family models produce confident garbage on near-silence. These are the
shapes that garbage actually takes on Thai meeting audio.
"""

from __future__ import annotations

import pytest

from sarai.models import LanguageHint
from sarai.worker.asr import (
    build_prompt,
    has_repeat_run,
    language_for,
    looks_hallucinated,
)


@pytest.mark.parametrize(
    "text",
    [
        "ครับ ครับ ครับ ครับ",  # spaced Thai loop
        "ครับครับครับครับครับ",  # run-on Thai loop, no word boundaries
        "yeah yeah yeah yeah yeah",
        "ok, ok, ok, ok, ok, ok",
        "ha ha ha ha ha ha ha",
    ],
)
def test_repetition_loops_are_caught(text: str) -> None:
    assert has_repeat_run(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "ตกลงตามนี้นะครับ เดี๋ยวผมส่งสไลด์ให้ทีมพรุ่งนี้",
        "We should deploy the new API เดือนหน้า ถ้า QA ผ่าน",
        "ครับ ผมเห็นด้วยครับ",  # a repeat, but only twice
        "ทำ ๆ กันไปก่อน",
        "1 2 3 4 5",
    ],
)
def test_real_speech_survives(text: str) -> None:
    assert has_repeat_run(text) is False
    assert looks_hallucinated(text, duration=4.0) is False


def test_short_segments_are_dropped() -> None:
    assert looks_hallucinated("ครับ", duration=0.2) is True
    assert looks_hallucinated("ครับ", duration=0.9) is False


def test_empty_and_boilerplate_are_dropped() -> None:
    assert looks_hallucinated("", duration=5.0) is True
    assert looks_hallucinated("   ", duration=5.0) is True
    assert looks_hallucinated("Thanks for watching!", duration=5.0) is True
    assert looks_hallucinated("ขอบคุณครับ", duration=5.0) is True


def test_boilerplate_inside_a_real_sentence_is_kept() -> None:
    """Only a segment that is *nothing but* boilerplate gets dropped."""
    assert looks_hallucinated("ขอบคุณครับ แล้วเรื่องงบประมาณล่ะครับ", duration=5.0) is False


def test_language_hint_maps_to_whisper_names() -> None:
    assert language_for(LanguageHint.TH) == "thai"
    assert language_for(LanguageHint.EN) == "english"
    # auto must stay None: a code-switched meeting needs per-turn detection.
    assert language_for(LanguageHint.AUTO) is None


def test_prompt_is_none_without_terms() -> None:
    assert build_prompt([], []) is None
    assert build_prompt(["   "], [""]) is None


def test_prompt_combines_glossary_and_names_without_duplicates() -> None:
    prompt = build_prompt(["Sarai", "deploy", "Sarai"], ["คุณสมชาย", "deploy"])
    assert prompt == "Sarai, deploy, คุณสมชาย"


def test_prompt_is_capped() -> None:
    prompt = build_prompt([f"term{i}" for i in range(200)], [])
    assert prompt is not None
    # Whisper keeps only the last 224 tokens of a prompt; an unbounded glossary
    # would push out the terms the user typed first.
    assert len(prompt) <= 400
