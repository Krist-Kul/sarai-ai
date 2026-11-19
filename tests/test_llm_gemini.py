"""GeminiChat: request shape and response/refusal handling, against a mock transport."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from sarai.config import Settings, get_settings
from sarai.llm.client import GeminiChat, LLMError, get_chat


def _settings(**update: Any) -> Settings:
    return get_settings().model_copy(
        update={"llm_provider": "gemini", "gemini_api_key": "test-key", **update}
    )


def _install(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> list[httpx.Request]:
    seen: list[httpx.Request] = []
    real = httpx.AsyncClient

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return real(*args, transport=httpx.MockTransport(record), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return seen


def _ok(parts: list[dict[str, Any]], finish: str = "STOP") -> httpx.Response:
    return httpx.Response(
        200, json={"candidates": [{"content": {"parts": parts}, "finishReason": finish}]}
    )


def test_get_chat_selects_gemini() -> None:
    chat = get_chat(_settings())
    assert isinstance(chat, GeminiChat)
    assert chat.model == "gemini-3.8-flash"


def test_missing_key_is_readable() -> None:
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        GeminiChat(_settings(gemini_api_key=None))


async def test_request_shape_and_text(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _install(
        monkeypatch,
        lambda _r: _ok([{"text": "thinking...", "thought": True}, {"text": '{"a": 1}'}]),
    )
    out = await GeminiChat(_settings()).complete("SYS", "USER")

    assert out == '{"a": 1}'
    req = seen[0]
    assert str(req.url) == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
    )
    assert req.headers["x-goog-api-key"] == "test-key"
    assert "key=" not in str(req.url)
    body = json.loads(req.content)
    assert body["systemInstruction"]["parts"][0]["text"] == "SYS"
    assert body["contents"] == [{"role": "user", "parts": [{"text": "USER"}]}]
    assert body["generationConfig"]["responseMimeType"] == "application/json"


async def test_http_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, lambda _r: httpx.Response(429, text="quota"))
    with pytest.raises(LLMError, match="Gemini returned 429"):
        await GeminiChat(_settings()).complete("s", "u")


async def test_blocked_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(
        monkeypatch,
        lambda _r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}),
    )
    with pytest.raises(LLMError, match="declined.*SAFETY"):
        await GeminiChat(_settings()).complete("s", "u")


async def test_safety_finish(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, lambda _r: _ok([], finish="SAFETY"))
    with pytest.raises(LLMError, match="declined"):
        await GeminiChat(_settings()).complete("s", "u")


async def test_empty_text(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, lambda _r: _ok([], finish="MAX_TOKENS"))
    with pytest.raises(LLMError, match="empty.*MAX_TOKENS"):
        await GeminiChat(_settings()).complete("s", "u")
