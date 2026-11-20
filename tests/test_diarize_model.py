"""Diarization model loading and output handling. pyannote and torch are
stubbed in sys.modules, so nothing is downloaded and the tests run in CI
without the worker group installed."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

from sarai.config import get_settings
from sarai.worker import diarize
from sarai.worker.stages import StageFailed

DEFAULT = "pyannote/speaker-diarization-community-1"


class MissingDependency(Exception):
    """Stand-in for pyannote.audio.utils.dependencies.MissingDependency."""


class _FakePipeline:
    def __init__(self, output: Any = None) -> None:
        self.device: Any = None
        self.output = output

    def to(self, device: Any) -> _FakePipeline:
        self.device = device
        return self

    def __call__(self, audio: Any) -> Any:
        return self.output


class _Loader:
    """Pipeline.from_pretrained stand-in: records calls, returns or raises."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.result: Any = _FakePipeline()
        self.error: Exception | None = None

    def from_pretrained(self, model: str, token: str | None = None) -> Any:
        self.calls.append((model, token))
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def loader(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Loader]:
    fake = _Loader()
    audio = ModuleType("pyannote.audio")
    audio.Pipeline = fake  # type: ignore[attr-defined]
    deps = ModuleType("pyannote.audio.utils.dependencies")
    deps.MissingDependency = MissingDependency  # type: ignore[attr-defined]
    torch = ModuleType("torch")
    torch.device = lambda name: SimpleNamespace(type=name)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyannote.audio", audio)
    monkeypatch.setitem(sys.modules, "pyannote.audio.utils.dependencies", deps)
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setattr(diarize, "_pipeline", None)
    monkeypatch.setattr(diarize, "_pipeline_failed", False)
    monkeypatch.setenv("HF_TOKEN", "hf_test")
    monkeypatch.setenv("DIARIZATION_DEVICE", "cpu")
    get_settings.cache_clear()
    yield fake
    get_settings.cache_clear()


def _select(monkeypatch: pytest.MonkeyPatch, model: str = DEFAULT) -> None:
    monkeypatch.setenv("DIARIZATION_MODEL", model)
    get_settings.cache_clear()


def test_default_model_is_unchanged() -> None:
    get_settings.cache_clear()
    assert type(get_settings()).model_fields["diarization_model"].default == DEFAULT


def test_selected_model_and_token_reach_from_pretrained(
    loader: _Loader, monkeypatch: pytest.MonkeyPatch
) -> None:
    _select(monkeypatch)
    pipeline = diarize.load_pipeline()
    assert pipeline is loader.result
    assert loader.calls == [(DEFAULT, "hf_test")]
    assert pipeline.device.type == "cpu"


def test_setup_error_is_a_permanent_job_failure() -> None:
    # StageFailed makes the worker fail the job once instead of retrying it.
    assert issubclass(diarize.DiarizationSetupError, StageFailed)


def test_pyannote_missing_dependency_is_not_degraded(
    loader: _Loader, monkeypatch: pytest.MonkeyPatch
) -> None:
    _select(monkeypatch)
    loader.error = MissingDependency("somepkg>=1.0 required")
    with pytest.raises(diarize.DiarizationSetupError, match="somepkg>=1.0"):
        diarize.load_pipeline()


def test_load_failure_points_at_both_pyannote_gates(
    loader: _Loader, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _select(monkeypatch)
    loader.error = OSError("403 Client Error")
    with caplog.at_level(logging.ERROR, logger="sarai.worker.diarize"):
        assert diarize.load_pipeline() is None
    assert "speaker-diarization-community-1" in caplog.text
    assert "segmentation-3.0" in caplog.text


def test_no_token_falls_back(loader: _Loader, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_TOKEN", "")
    _select(monkeypatch)
    assert diarize.load_pipeline() is None
    assert loader.calls == []


# --- output handling -------------------------------------------------------


class _Annotation:
    def __init__(self, tracks: list[tuple[float, float, str]]) -> None:
        self.tracks = tracks

    def itertracks(self, yield_label: bool = False) -> Iterator[tuple[Any, str, str]]:
        for start, end, speaker in self.tracks:
            yield SimpleNamespace(start=start, end=end), "_", speaker


SR = 16_000


def test_diarize_reads_the_exclusive_annotation(
    loader: _Loader, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Overlap from 4 to 6 s: the overlapping variant would send it to ASR twice.
    output = SimpleNamespace(
        speaker_diarization=_Annotation([(0.0, 6.0, "A"), (4.0, 10.0, "B")]),
        exclusive_speaker_diarization=_Annotation([(0.0, 5.0, "A"), (5.0, 10.0, "B")]),
    )
    loader.result = _FakePipeline(output)
    _select(monkeypatch)
    turns = diarize.diarize(Path("x.wav"), None, SR)
    assert [(t.start, t.end, t.speaker) for t in turns] == [(0.0, 5.0, "A"), (5.0, 10.0, "B")]


def test_unavailable_pipeline_falls_back_to_one_speaker(
    loader: _Loader, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HF_TOKEN", "")
    _select(monkeypatch)
    samples = np.zeros(SR * 3, dtype=np.float32)
    turns = diarize.diarize(Path("x.wav"), samples, SR)
    assert {t.speaker for t in turns} == {"SPEAKER_00"}
    assert turns[0].start == 0.0
    assert turns[-1].end == pytest.approx(3.0)
