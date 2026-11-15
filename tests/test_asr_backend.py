"""Backend selection.

The choice has to be right on a machine none of the CI runners are, so the two
inputs it reads -- the resolved torch device and whether mlx_whisper imports --
are stubbed rather than detected.
"""

from __future__ import annotations

import math

import pytest

from sarai.config import get_settings
from sarai.worker import asr, asr_mlx


@pytest.fixture(autouse=True)
def _clear_backend_cache() -> None:
    asr._backend = None


def _hardware(monkeypatch: pytest.MonkeyPatch, device: str, mlx: bool) -> None:
    monkeypatch.setattr(asr, "resolve_device", lambda: device)
    monkeypatch.setattr(asr_mlx, "available", lambda: mlx)


def test_cuda_keeps_transformers_even_where_mlx_would_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _hardware(monkeypatch, "cuda", mlx=True)
    assert asr.detect_backend() == "transformers"


def test_apple_silicon_without_cuda_uses_mlx(monkeypatch: pytest.MonkeyPatch) -> None:
    _hardware(monkeypatch, "mps", mlx=True)
    assert asr.detect_backend() == "mlx"


def test_apple_silicon_falls_back_when_mlx_is_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _hardware(monkeypatch, "mps", mlx=False)
    assert asr.detect_backend() == "transformers"


def test_cpu_box_uses_transformers(monkeypatch: pytest.MonkeyPatch) -> None:
    _hardware(monkeypatch, "cpu", mlx=False)
    assert asr.detect_backend() == "transformers"


def test_pinning_the_device_to_cpu_opts_out_of_mlx(monkeypatch: pytest.MonkeyPatch) -> None:
    """ASR_DEVICE=cpu on a Mac means cpu, not 'the fast thing anyway'."""
    _hardware(monkeypatch, "cpu", mlx=True)
    assert asr.detect_backend() == "transformers"


def test_an_explicit_backend_wins_over_the_hardware(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASR_BACKEND", "mlx")
    get_settings.cache_clear()
    _hardware(monkeypatch, "cuda", mlx=False)
    assert asr.detect_backend() == "mlx"


def test_the_backend_is_resolved_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """It is asked once per turn; re-detecting would import torch every time."""
    calls = 0

    def counted() -> str:
        nonlocal calls
        calls += 1
        return "transformers"

    monkeypatch.setattr(asr, "detect_backend", counted)
    assert [asr.resolve_backend() for _ in range(3)] == ["transformers"] * 3
    assert calls == 1


# ---------------------------------------------------------------------------
# Confidence, which the two backends compute from different raw material
# ---------------------------------------------------------------------------


def test_confidence_is_the_exponentiated_mean_logprob() -> None:
    result = {"segments": [{"avg_logprob": -0.2}, {"avg_logprob": -0.4}]}
    assert asr_mlx._confidence(result) == pytest.approx(math.exp(-0.3))


def test_confidence_lands_in_the_same_0_to_1_range_as_the_torch_path() -> None:
    value = asr_mlx._confidence({"segments": [{"avg_logprob": -0.05}]})
    assert value is not None
    assert 0.0 < value <= 1.0


def test_confidence_is_none_when_a_segment_carries_no_usable_score() -> None:
    assert asr_mlx._confidence({"segments": []}) is None
    assert asr_mlx._confidence({}) is None
    assert asr_mlx._confidence({"segments": [{"avg_logprob": float("-inf")}]}) is None


def test_mlx_is_never_offered_off_apple_silicon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    assert asr_mlx.available() is False
