"""ASR: Typhoon Whisper, loaded once, run per speaker turn.

Per-turn transcription (rather than transcribing the whole file and aligning
speakers afterwards) buys two things: speaker attribution that is right by
construction, and far less hallucination, because the silence between turns
never reaches the model.

torch and transformers are imported inside the loader so the pure text helpers
below can be imported and tested without them.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

import numpy as np

from sarai.config import get_settings
from sarai.models import LanguageHint
from sarai.worker.diarize import resolve_device

log = logging.getLogger("sarai.worker.asr")

SAMPLE_RATE = 16_000
MIN_SEGMENT_SECONDS = 0.3
MAX_REPEATS = 3

_model: Any | None = None
_processor: Any | None = None


@dataclass(frozen=True)
class Transcription:
    text: str
    confidence: float | None


# ---------------------------------------------------------------------------
# Hallucination guard -- pure, no torch
# ---------------------------------------------------------------------------

# Whisper's canned outputs for silence. Thai models inherit the habit and add
# their own; these are the ones that show up in practice on meeting audio.
BOILERPLATE = {
    "ขอบคุณครับ",
    "ขอบคุณค่ะ",
    "สวัสดีครับ",
    "สวัสดีค่ะ",
    "โปรดติดตามตอนต่อไป",
    "thank you.",
    "thanks for watching!",
    "you",
    "bye.",
    "。",
}


def normalize_for_compare(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip().lower()


def has_repeat_run(text: str, max_repeats: int = MAX_REPEATS) -> bool:
    """True if some token or short phrase repeats more than `max_repeats` times.

    Two passes, because Thai and English fail differently. English loops arrive
    space-separated ("yeah yeah yeah yeah"); Thai has no word boundaries, so the
    same loop arrives as one run-on string ("ครับครับครับครับ") and only a
    character-level check catches it.
    """
    stripped = normalize_for_compare(text)
    if not stripped:
        return False

    words = stripped.split()
    run = 1
    for prev, cur in zip(words, words[1:], strict=False):
        run = run + 1 if cur == prev else 1
        if run > max_repeats:
            return True

    # Character n-grams: a unit of 1-12 chars repeated back to back.
    compact = re.sub(r"\s+", "", stripped)
    for unit in range(1, 13):
        if len(compact) < unit * (max_repeats + 1):
            break
        for start in range(0, len(compact) - unit * (max_repeats + 1) + 1):
            chunk = compact[start : start + unit]
            repeated = chunk * (max_repeats + 1)
            if compact.startswith(repeated, start):
                return True
    return False


def looks_hallucinated(text: str, duration: float) -> bool:
    """Drop a segment that is too short to carry speech, empty, boilerplate, or
    a repetition loop."""
    if duration < MIN_SEGMENT_SECONDS:
        return True
    stripped = normalize_for_compare(text)
    if not stripped:
        return True
    if stripped in BOILERPLATE:
        return True
    return has_repeat_run(text)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


def _dtype(device: str) -> Any:
    import torch

    # fp16 is a large win on CUDA. On MPS and CPU it is either unsupported or
    # slower than fp32 for this model, and it makes Thai output measurably worse.
    return torch.float16 if device == "cuda" else torch.float32


def load_model() -> tuple[Any, Any, str]:
    """Load processor + model once into module globals. Returns (model, processor, device)."""
    global _model, _processor
    settings = get_settings()
    device = resolve_device()
    if _model is not None and _processor is not None:
        return _model, _processor, device

    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

    log.info("loading ASR model %s on %s", settings.asr_model, device)
    processor = AutoProcessor.from_pretrained(settings.asr_model)  # type: ignore[no-untyped-call]
    model = AutoModelForSpeechSeq2Seq.from_pretrained(
        settings.asr_model,
        dtype=_dtype(device),
        low_cpu_mem_usage=True,
    )
    model.to(device)
    model.eval()
    _model, _processor = model, processor
    log.info("ASR model ready on %s", device)
    return model, processor, device


def language_for(hint: LanguageHint) -> str | None:
    """None lets Whisper detect per turn, which is what a code-switched meeting
    needs; an explicit hint pins every turn to one language."""
    if hint is LanguageHint.TH:
        return "thai"
    if hint is LanguageHint.EN:
        return "english"
    return None


def build_prompt(glossary: list[str], speaker_names: list[str]) -> str | None:
    """Vocabulary hint for Whisper, assembled from the meeting's glossary.

    Whisper conditions on a text prefix, which biases decoding toward the
    spellings it contains. This is what makes the glossary earn the promise the
    upload screen makes: without it, "roadmap" comes back transliterated into
    Thai script and no downstream step can reliably tell that from a real Thai
    word.
    """
    terms = [t.strip() for t in [*glossary, *speaker_names] if t.strip()]
    if not terms:
        return None
    # Whisper truncates the prompt to the last 224 tokens; keep it short so the
    # terms that survive are the ones the user actually cared about.
    return ", ".join(dict.fromkeys(terms))[:400]


def transcribe(samples: np.ndarray, hint: LanguageHint, prompt: str | None = None) -> Transcription:
    """Transcribe one speaker turn of 16 kHz mono audio."""
    import torch

    model, processor, device = load_model()
    inputs = processor(
        samples, sampling_rate=SAMPLE_RATE, return_tensors="pt", return_attention_mask=True
    )
    features = inputs.input_features.to(device=device, dtype=_dtype(device))
    attention_mask = getattr(inputs, "attention_mask", None)
    if attention_mask is not None:
        attention_mask = attention_mask.to(device)

    kwargs: dict[str, Any] = {
        "task": "transcribe",
        "return_dict_in_generate": True,
        "output_scores": True,
        # Whisper loops on near-silence; this is the cheapest brake available.
        "no_repeat_ngram_size": 4,
    }
    language = language_for(hint)
    if language is not None:
        kwargs["language"] = language
    if attention_mask is not None:
        kwargs["attention_mask"] = attention_mask

    prompt_text = (prompt or "").strip()
    if prompt_text:
        kwargs["prompt_ids"] = processor.get_prompt_ids(prompt_text, return_tensors="pt").to(device)

    with torch.no_grad():
        output = model.generate(features, **kwargs)

    sequences = output.sequences
    text = processor.batch_decode(sequences, skip_special_tokens=True)[0].strip()
    # The prompt is echoed back at the front of the decoded text; drop it, or
    # every segment starts with the glossary.
    if prompt_text and text.startswith(prompt_text):
        text = text[len(prompt_text) :].strip()

    confidence: float | None = None
    try:
        scores = model.compute_transition_scores(sequences, output.scores, normalize_logits=True)
        finite = scores[0][torch.isfinite(scores[0])]
        if finite.numel() > 0:
            confidence = float(torch.exp(finite.mean()).item())
    except Exception:  # noqa: BLE001 - confidence is a nice-to-have, never fatal
        log.debug("could not compute confidence for a turn", exc_info=True)

    return Transcription(text=text, confidence=confidence)
