"""Transient provider failures are retried; real refusals are not.

Gemini answers 503 "high demand" and 429 for minutes at a time, and before
these retries every one of them failed the whole summarize job on the spot.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

import sarai.llm.client as client_mod
from sarai.config import Settings, get_settings
from sarai.llm.client import DeepSeekChat, GeminiChat, LLMError


def _settings(**update: Any) -> Settings:
    return get_settings().model_copy(
        update={
            "gemini_api_key": "g",
            "deepseek_api_key": "d",
            "llm_retries": 3,
            **update,
        }
    )


@pytest.fixture
def waits(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record backoff waits instead of sleeping through them."""
    seen: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        seen.append(seconds)

    monkeypatch.setattr(client_mod, "_sleep", fake_sleep)
    return seen


def _serve(
    monkeypatch: pytest.MonkeyPatch, responses: list[Callable[[], httpx.Response]]
) -> list[httpx.Request]:
    """Answer each request with the next queued response factory."""
    seen: list[httpx.Request] = []
    real = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responses.pop(0)()

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return real(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return seen


def _gemini_ok() -> httpx.Response:
    return httpx.Response(
        200, json={"candidates": [{"content": {"parts": [{"text": "{}"}]}, "finishReason": "STOP"}]}
    )


def _deepseek_ok() -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})


def _status(code: int, **headers: str) -> Callable[[], httpx.Response]:
    return lambda: httpx.Response(code, text="busy", headers=headers)


def _drop() -> httpx.Response:
    raise httpx.ConnectError("connection reset")


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
async def test_gemini_retries_transient_status(
    monkeypatch: pytest.MonkeyPatch, waits: list[float], code: int
) -> None:
    seen = _serve(monkeypatch, [_status(code), _status(code), _gemini_ok])
    assert await GeminiChat(_settings()).complete("s", "u") == "{}"
    assert len(seen) == 3
    assert len(waits) == 2


async def test_deepseek_retries_a_dropped_connection(
    monkeypatch: pytest.MonkeyPatch, waits: list[float]
) -> None:
    seen = _serve(monkeypatch, [_drop, _deepseek_ok])
    assert await DeepSeekChat(_settings()).complete("s", "u") == "{}"
    assert len(seen) == 2


async def test_client_errors_are_not_retried(
    monkeypatch: pytest.MonkeyPatch, waits: list[float]
) -> None:
    seen = _serve(monkeypatch, [_status(400), _gemini_ok])
    with pytest.raises(LLMError, match="Gemini returned 400"):
        await GeminiChat(_settings()).complete("s", "u")
    assert len(seen) == 1
    assert waits == []


async def test_gives_up_after_the_retry_budget(
    monkeypatch: pytest.MonkeyPatch, waits: list[float]
) -> None:
    seen = _serve(monkeypatch, [_status(503)] * 4)
    with pytest.raises(LLMError, match="Gemini returned 503"):
        await GeminiChat(_settings()).complete("s", "u")
    assert len(seen) == 4  # first try + 3 retries


async def test_retry_after_header_is_honoured_up_to_the_cap(
    monkeypatch: pytest.MonkeyPatch, waits: list[float]
) -> None:
    _serve(
        monkeypatch,
        [_status(429, **{"retry-after": "7"}), _status(429, **{"retry-after": "9999"}), _gemini_ok],
    )
    await GeminiChat(_settings(llm_retry_max_wait_seconds=60)).complete("s", "u")
    assert waits == [7.0, 60.0]


async def test_backoff_grows(monkeypatch: pytest.MonkeyPatch, waits: list[float]) -> None:
    _serve(monkeypatch, [_status(503)] * 3 + [_gemini_ok])
    await GeminiChat(_settings()).complete("s", "u")
    assert waits == sorted(waits) and waits[0] < waits[-1]


async def test_gemini_truncated_output_is_named(
    monkeypatch: pytest.MonkeyPatch, waits: list[float]
) -> None:
    truncated = lambda: httpx.Response(  # noqa: E731
        200,
        json={
            "candidates": [
                {"content": {"parts": [{"text": '{"title": "x'}]}, "finishReason": "MAX_TOKENS"}
            ]
        },
    )
    _serve(monkeypatch, [truncated])
    with pytest.raises(LLMError, match="cut off"):
        await GeminiChat(_settings()).complete("s", "u")
