"""MLX ASR backend, for Apple Silicon.

Same weights as the transformers path, converted to MLX. On an M-series machine
that conversion is the difference between a usable local transcriber and one
that runs slower than the meeting did: transformers-on-mps falls back to CPU for
several Whisper ops, MLX does not.

`mlx_whisper` and `mlx` are imported inside the functions. They only install on
Apple Silicon, and the worker has to keep importing on every other machine.
"""

from __future__ import annotations

import importlib.util
import logging
import math
import platform
from typing import Any

import numpy as np

from sarai.config import get_settings

log = logging.getLogger("sarai.worker.asr_mlx")


def available() -> bool:
    """Apple Silicon with mlx_whisper installed. Checked without importing it:
    a missing optional dependency must not cost an ImportError on every start."""
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        return False
    return importlib.util.find_spec("mlx_whisper") is not None


def warm() -> None:
    """Populate mlx_whisper's model cache before the first job claims a turn.

    mlx_whisper caches the model on a class attribute keyed by repo, so this is
    a real preload and not just a download: the first transcribe() call after it
    finds the weights already in memory.
    """
    import mlx as _mlx  # noqa: F401  -- fail here, not four frames deep
    import mlx.core as mx
    from mlx_whisper.transcribe import ModelHolder

    repo = get_settings().asr_model_mlx
    log.info("loading MLX ASR model %s", repo)
    # fp16 matches mlx_whisper's own default in transcribe(); loading in one
    # dtype and decoding in another would reload the weights on the first turn.
    ModelHolder.get_model(repo, mx.float16)
    log.info("MLX ASR model ready")


# Whisper's own fallback thresholds, as mlx_whisper.transcribe applies them.
TEMPERATURES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
COMPRESSION_RATIO_THRESHOLD = 2.4
LOGPROB_THRESHOLD = -1.0
NO_SPEECH_THRESHOLD = 0.6


def transcribe(
    samples: np.ndarray, language: str | None, prompt: str | None = None
) -> tuple[str, float | None]:
    """One speaker turn. Returns (text, confidence) for the caller to wrap.

    `language` is Whisper's own name for it ("thai"), not a LanguageHint --
    resolving the hint stays in asr.py so both backends answer to one rule.

    Turns are at most one 30 s window, so this decodes that window directly
    instead of going through mlx_whisper.transcribe(). The difference is the
    encoder: transcribe() runs the 32-layer encoder once for language detection
    and again for every temperature it falls back to, while here it runs once
    and the features are shared. On an M4 that is roughly 2 s saved per turn
    with language=auto, and most of a fallback's cost.
    """
    from mlx_whisper.audio import N_FRAMES, N_SAMPLES

    if samples.shape[0] > N_SAMPLES:
        return _transcribe_long(samples, language, prompt)

    import mlx.core as mx
    from mlx_whisper.audio import log_mel_spectrogram, pad_or_trim
    from mlx_whisper.decoding import DecodingOptions
    from mlx_whisper.transcribe import ModelHolder

    model = ModelHolder.get_model(get_settings().asr_model_mlx, mx.float16)
    # Same framing as transcribe(): mel of the clip padded with 30 s of silence,
    # cut to the clip's own frames, then zero-padded to one window.
    mel = log_mel_spectrogram(samples, n_mels=model.dims.n_mels, padding=N_SAMPLES)
    content_frames = mel.shape[-2] - N_FRAMES
    segment = pad_or_trim(mel[:content_frames], N_FRAMES, axis=-2).astype(mx.float16)
    features = model.encoder(segment[None])

    if language is None:
        _, probs = model.detect_language(features)
        language = max(probs[0], key=probs[0].get)

    prompt_text = (prompt or "").strip()
    result = None
    for temperature in TEMPERATURES:
        options = DecodingOptions(
            task="transcribe",
            language=language,
            temperature=temperature,
            # mlx_whisper strips the prompt tokens back off before decoding, so
            # nothing has to be trimmed afterwards.
            prompt=" " + prompt_text if prompt_text else None,
            without_timestamps=False,
            fp16=True,
        )
        result = model.decode(features, options)[0]
        if result.no_speech_prob > NO_SPEECH_THRESHOLD:
            break  # silence: a hotter sample will not find words that are not there
        if (
            result.compression_ratio <= COMPRESSION_RATIO_THRESHOLD
            and result.avg_logprob >= LOGPROB_THRESHOLD
        ):
            break

    assert result is not None
    if result.no_speech_prob > NO_SPEECH_THRESHOLD and result.avg_logprob < LOGPROB_THRESHOLD:
        return "", None  # transcribe() skips this window; the guard drops the turn
    confidence = math.exp(result.avg_logprob) if math.isfinite(result.avg_logprob) else None
    return result.text.strip(), confidence


def _transcribe_long(
    samples: np.ndarray, language: str | None, prompt: str | None
) -> tuple[str, float | None]:
    """More than one window: let mlx_whisper do the seeking. Turn shaping caps
    turns at 30 s, so this is only reached by a turn that slipped past it."""
    import mlx_whisper

    options: dict[str, Any] = {
        "path_or_hf_repo": get_settings().asr_model_mlx,
        # Each call is one turn, so there is no previous window worth
        # conditioning on -- and letting it try invites drift.
        "condition_on_previous_text": False,
    }
    if language is not None:
        options["language"] = language
    prompt_text = (prompt or "").strip()
    if prompt_text:
        options["initial_prompt"] = prompt_text

    result = mlx_whisper.transcribe(samples, **options)
    return str(result.get("text", "")).strip(), _confidence(result)


def _confidence(result: dict[str, Any]) -> float | None:
    """Mean segment log-probability, exponentiated.

    The transformers path derives its confidence from per-token transition
    scores. Both land on the same 0..1 scale, which is what the review screen
    colours its low-confidence rows by.
    """
    logprobs = [
        float(s["avg_logprob"])
        for s in result.get("segments") or []
        if isinstance(s, dict) and math.isfinite(float(s.get("avg_logprob", float("-inf"))))
    ]
    if not logprobs:
        return None
    return math.exp(sum(logprobs) / len(logprobs))
