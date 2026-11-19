"""Diarization model selection: the default pyannote pipeline vs the opt-in
SUPlime one. pyannote and torch are stubbed in sys.modules, so nothing is
downloaded and the tests run in CI without the worker group installed."""

from __future__ import annotations

import importlib.util
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
SUPLIME = "rewayai/suplime-large"


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


def _select(monkeypatch: pytest.MonkeyPatch, model: str, *, suplime_installed: bool) -> None:
    monkeypatch.setenv("DIARIZATION_MODEL", model)
    get_settings.cache_clear()
    real_find_spec = importlib.util.find_spec

    def find_spec(name: str, *args: Any) -> Any:
        if name == "suplime":
            return object() if suplime_installed else None
        return real_find_spec(name, *args)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec)


def test_default_model_is_unchanged() -> None:
    get_settings.cache_clear()
    assert type(get_settings()).model_fields["diarization_model"].default == DEFAULT


@pytest.mark.parametrize(
    ("model", "expected"),
    [(DEFAULT, False), (SUPLIME, True), ("rewayai/suplime", True), ("RewayAI/SUPlime-Large", True)],
)
def test_is_suplime(model: str, expected: bool) -> None:
    assert diarize.is_suplime(model) is expected


def test_license_warning_only_for_non_commercial_models() -> None:
    assert diarize.license_warning(DEFAULT) is None
    warning = diarize.license_warning(SUPLIME)
    assert warning is not None
    assert "CC BY-NC 4.0" in warning
    assert "\n" not in warning


def test_selected_model_and_token_reach_from_pretrained(
    loader: _Loader, monkeypatch: pytest.MonkeyPatch
) -> None:
    _select(monkeypatch, SUPLIME, suplime_installed=True)
    pipeline = diarize.load_pipeline()
    assert pipeline is loader.result
    assert loader.calls == [(SUPLIME, "hf_test")]
    assert pipeline.device.type == "cpu"


def test_missing_suplime_package_fails_loudly(
    loader: _Loader, monkeypatch: pytest.MonkeyPatch
) -> None:
    _select(monkeypatch, SUPLIME, suplime_installed=False)
    with pytest.raises(diarize.DiarizationSetupError, match="make install-suplime"):
        diarize.load_pipeline()
    assert loader.calls == []
    # A configuration error, not a degraded mode: the next call fails again.
    assert diarize._pipeline_failed is False


def test_missing_suplime_fails_even_without_a_token(
    loader: _Loader, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HF_TOKEN", "")
    _select(monkeypatch, SUPLIME, suplime_installed=False)
    with pytest.raises(diarize.DiarizationSetupError):
        diarize.load_pipeline()


def test_missing_suplime_is_a_permanent_job_failure() -> None:
    # StageFailed makes the worker fail the job once instead of retrying it.
    assert issubclass(diarize.DiarizationSetupError, StageFailed)


def test_pyannote_missing_dependency_is_not_degraded(
    loader: _Loader, monkeypatch: pytest.MonkeyPatch
) -> None:
    _select(monkeypatch, SUPLIME, suplime_installed=True)
    loader.error = MissingDependency("suplime>=0.3 required")
    with pytest.raises(diarize.DiarizationSetupError, match="suplime>=0.3"):
        diarize.load_pipeline()


def test_missing_suplime_does_not_affect_the_default_model(
    loader: _Loader, monkeypatch: pytest.MonkeyPatch
) -> None:
    _select(monkeypatch, DEFAULT, suplime_installed=False)
    assert diarize.load_pipeline() is loader.result


def test_suplime_load_failure_names_suplime_not_pyannote_gates(
    loader: _Loader, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _select(monkeypatch, SUPLIME, suplime_installed=True)
    loader.error = OSError("401 Client Error")
    with caplog.at_level(logging.ERROR, logger="sarai.worker.diarize"):
        assert diarize.load_pipeline() is None
    assert "huggingface.co/rewayai/suplime-large" in caplog.text
    assert "segmentation-3.0" not in caplog.text


def test_default_load_failure_still_points_at_both_pyannote_gates(
    loader: _Loader, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _select(monkeypatch, DEFAULT, suplime_installed=False)
    loader.error = OSError("403 Client Error")
    with caplog.at_level(logging.ERROR, logger="sarai.worker.diarize"):
        assert diarize.load_pipeline() is None
    assert "speaker-diarization-community-1" in caplog.text
    assert "segmentation-3.0" in caplog.text


def test_no_token_still_falls_back_for_either_model(
    loader: _Loader, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HF_TOKEN", "")
    for model in (DEFAULT, SUPLIME):
        _select(monkeypatch, model, suplime_installed=True)
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
    _select(monkeypatch, SUPLIME, suplime_installed=True)
    turns = diarize.diarize(Path("x.wav"), None, SR)
    assert [(t.start, t.end, t.speaker) for t in turns] == [(0.0, 5.0, "A"), (5.0, 10.0, "B")]


def test_unavailable_pipeline_falls_back_to_one_speaker(
    loader: _Loader, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HF_TOKEN", "")
    _select(monkeypatch, DEFAULT, suplime_installed=False)
    samples = np.zeros(SR * 3, dtype=np.float32)
    turns = diarize.diarize(Path("x.wav"), samples, SR)
    assert {t.speaker for t in turns} == {"SPEAKER_00"}
    assert turns[0].start == 0.0
    assert turns[-1].end == pytest.approx(3.0)
