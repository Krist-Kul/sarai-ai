"""Diarization device choice and the mps -> cpu safety net. Stubbed: the real
pipeline needs gated weights and minutes of compute."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from sarai.config import get_settings
from sarai.worker import diarize


@pytest.fixture(autouse=True)
def _fresh_settings() -> Any:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_auto_follows_the_asr_device(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diarize, "resolve_device", lambda: "mps")
    monkeypatch.setenv("DIARIZATION_DEVICE", "auto")
    assert diarize.diarization_device() == "mps"


def test_explicit_device_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diarize, "resolve_device", lambda: "mps")
    monkeypatch.setenv("DIARIZATION_DEVICE", "cpu")
    assert diarize.diarization_device() == "cpu"


class _Pipeline:
    def __init__(self, device: str, fail_on: str | None) -> None:
        self.device = SimpleNamespace(type=device)
        self.fail_on = fail_on
        self.runs: list[str] = []

    def to(self, device: Any) -> _Pipeline:
        self.device = SimpleNamespace(type=device.type)
        return self

    def __call__(self, audio: Any) -> str:
        self.runs.append(self.device.type)
        if self.device.type == self.fail_on:
            raise NotImplementedError("op not implemented for 'mps'")
        return "annotation"


def test_mps_failure_retries_on_cpu_and_stays_there() -> None:
    pytest.importorskip("torch")  # CI installs the api group only
    pipeline = _Pipeline("mps", fail_on="mps")
    assert diarize._run_pipeline(pipeline, {}) == "annotation"
    assert pipeline.runs == ["mps", "cpu"]
    assert pipeline.device.type == "cpu"


def test_cpu_failure_is_not_swallowed() -> None:
    pipeline = _Pipeline("cpu", fail_on="cpu")
    with pytest.raises(NotImplementedError):
        diarize._run_pipeline(pipeline, {})


class _OomPipeline:
    """Runs out of CUDA memory until both batch sizes are at or below `fits`."""

    def __init__(self, fits: int) -> None:
        self.device = SimpleNamespace(type="cuda")
        self.embedding_batch_size = 32
        self.segmentation_batch_size = 32
        self.fits = fits
        self.runs: list[tuple[int, int]] = []

    def __call__(self, audio: Any) -> str:
        self.runs.append((self.embedding_batch_size, self.segmentation_batch_size))
        if max(self.embedding_batch_size, self.segmentation_batch_size) > self.fits:
            raise RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")
        return "annotation"


def test_cuda_oom_shrinks_batches_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    torch = pytest.importorskip("torch")
    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: None)
    pipeline = _OomPipeline(fits=2)
    assert diarize._run_pipeline(pipeline, {}) == "annotation"
    assert pipeline.runs == [(32, 32), (8, 8), (2, 2)]
    # Kept small for the next job instead of paying for the same OOM again.
    assert pipeline.embedding_batch_size == 2


def test_cuda_oom_at_batch_one_is_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    torch = pytest.importorskip("torch")
    monkeypatch.setattr(torch.cuda, "empty_cache", lambda: None)
    pipeline = _OomPipeline(fits=0)
    with pytest.raises(RuntimeError, match="out of memory"):
        diarize._run_pipeline(pipeline, {})
    assert pipeline.runs[-1] == (1, 1)
