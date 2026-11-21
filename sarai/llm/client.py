"""Chat clients.

Three providers, one method. The summarizer only ever needs "here is a system
prompt and a user message, give me back text", so that is the whole interface --
map-reduce and schema validation live in `sarai.llm.summarize` and work
identically against any provider. Temporary provider failures (rate limits,
overload, dropped connections) are retried here, below that interface, so
every caller gets them.

Both are text-only. Audio never reaches them; that is the entire point of the
architecture and it is enforced here by there being no way to send bytes.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

import httpx

from sarai.config import Settings

# Non-streaming: minutes for a 90-minute meeting land well inside this, and the
# SDK's own HTTP timeout is the backstop. Anything larger would need streaming.
MAX_TOKENS = 16_000

log = logging.getLogger("sarai.llm")

# Statuses that mean "not now", not "no": rate limits, overload, gateway
# trouble. Everything else (400 bad request, 401/403 key, 404 model) fails
# at once -- retrying cannot fix it.
TRANSIENT_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504, 529})

# Module-level so tests can skip the waits.
_sleep = asyncio.sleep


class LLMError(RuntimeError):
    """The provider refused, failed, or returned something unusable."""


class Chat(Protocol):
    """One completion call. The model name is carried so it can be recorded
    alongside the summary -- minutes are only reproducible if you know which
    model wrote them."""

    model: str

    async def complete(self, system: str, user: str) -> str: ...


def _retry_after(res: httpx.Response) -> float | None:
    value = res.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None  # an HTTP date; fall back to our own backoff


async def post_with_retry(
    provider: str,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    settings: Settings,
) -> httpx.Response:
    """POST, retrying temporary failures with backoff.

    Returns the final response, which may still be an error status: the
    caller turns it into an LLMError with the provider's own message.
    """
    attempts = settings.llm_retries + 1
    for attempt in range(1, attempts + 1):
        res: httpx.Response | None = None
        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
                res = await client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            if attempt == attempts:
                raise LLMError(f"Could not reach {provider}: {exc}") from exc
            reason = f"{type(exc).__name__}: {exc}"
        else:
            if res.status_code not in TRANSIENT_STATUSES or attempt == attempts:
                return res
            reason = f"{res.status_code} {res.text[:120]}"

        backoff = 2.0**attempt  # 2, 4, 8, 16, 32...
        hinted = _retry_after(res) if res is not None else None
        wait = min(hinted if hinted is not None else backoff, settings.llm_retry_max_wait_seconds)
        log.warning(
            "%s request failed (%s); retry %d of %d in %.0fs",
            provider,
            reason,
            attempt,
            attempts - 1,
            wait,
        )
        await _sleep(wait)
    raise AssertionError("unreachable")  # pragma: no cover


class DeepSeekChat:
    """DeepSeek's OpenAI-compatible /chat/completions endpoint."""

    def __init__(self, settings: Settings) -> None:
        if not settings.deepseek_api_key:
            raise LLMError("DEEPSEEK_API_KEY is not set")
        self.model = settings.deepseek_model
        self._key = settings.deepseek_api_key
        self._url = settings.deepseek_base_url.rstrip("/") + "/chat/completions"
        self._settings = settings

    async def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            # The endpoint's own JSON mode. The response is still validated
            # against MinutesJSON -- valid JSON is not a valid schema.
            "response_format": {"type": "json_object"},
        }
        res = await post_with_retry(
            "DeepSeek",
            self._url,
            headers={"Authorization": f"Bearer {self._key}"},
            payload=payload,
            settings=self._settings,
        )

        if res.status_code != 200:
            raise LLMError(f"DeepSeek returned {res.status_code}: {res.text[:300]}")
        try:
            body = res.json()
            return str(body["choices"][0]["message"]["content"])
        except (ValueError, KeyError, IndexError) as exc:
            raise LLMError(f"DeepSeek returned an unexpected body: {res.text[:300]}") from exc


class AnthropicChat:
    """Anthropic Messages API, through the official SDK."""

    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set")
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover - dependency is in the worker group
            raise LLMError(
                "LLM_PROVIDER=anthropic needs the `anthropic` package (uv sync --group worker)"
            ) from exc

        self.model = settings.anthropic_model
        self._client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            timeout=settings.llm_timeout_seconds,
            # The SDK retries 429/5xx/connection errors itself, with backoff.
            max_retries=settings.llm_retries,
        )

    async def complete(self, system: str, user: str) -> str:
        try:
            message = await self._client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:  # noqa: BLE001 - SDK raises a family of errors
            raise LLMError(f"Anthropic request failed: {type(exc).__name__}: {exc}") from exc

        # A safety decline arrives as a normal 200 with an empty or partial
        # body, so it has to be checked before reading the content.
        if message.stop_reason == "refusal":
            raise LLMError("Anthropic declined to summarize this transcript")
        text = "".join(block.text for block in message.content if block.type == "text")
        if not text.strip():
            raise LLMError("Anthropic returned an empty response")
        return text


class GeminiChat:
    """Google Gemini API (generativelanguage.googleapis.com), plain REST.

    Called over httpx rather than the google-genai SDK: the request is one
    POST, and keeping it SDK-free means the API process gains no dependency.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        self.model = settings.gemini_model
        self._key = settings.gemini_api_key
        self._url = (
            f"{settings.gemini_base_url.rstrip('/')}/v1beta/models/{self.model}:generateContent"
        )
        self._settings = settings

    async def complete(self, system: str, user: str) -> str:
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                # On thinking models this budget includes thinking tokens.
                "maxOutputTokens": MAX_TOKENS,
                # JSON mode. The response is still validated against
                # MinutesJSON -- valid JSON is not a valid schema.
                "responseMimeType": "application/json",
            },
        }
        res = await post_with_retry(
            "Gemini",
            self._url,
            # Header, not ?key=, so the key never lands in a logged URL.
            headers={"x-goog-api-key": self._key},
            payload=payload,
            settings=self._settings,
        )

        if res.status_code != 200:
            raise LLMError(f"Gemini returned {res.status_code}: {res.text[:300]}")
        try:
            body = res.json()
        except ValueError as exc:
            raise LLMError(f"Gemini returned an unexpected body: {res.text[:300]}") from exc

        # A blocked prompt is a 200 with no candidates and a blockReason.
        block = (body.get("promptFeedback") or {}).get("blockReason")
        if block:
            raise LLMError(f"Gemini declined to summarize this transcript ({block})")
        candidates = body.get("candidates") or []
        if not candidates:
            raise LLMError(f"Gemini returned no candidates: {res.text[:300]}")
        candidate = candidates[0]
        finish = candidate.get("finishReason")
        if finish in {"SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"}:
            raise LLMError(f"Gemini declined to summarize this transcript ({finish})")
        parts = (candidate.get("content") or {}).get("parts") or []
        # Thinking models may return thought-summary parts; skip them.
        text = "".join(
            str(p.get("text", "")) for p in parts if isinstance(p, dict) and not p.get("thought")
        )
        if finish == "MAX_TOKENS":
            # Truncated JSON would otherwise surface as a baffling schema error.
            raise LLMError(
                f"Gemini's answer was cut off at the {MAX_TOKENS}-token output limit. "
                "Lower LLM_SINGLE_CALL_CHARS / LLM_CHUNK_CHARS so each call is smaller."
            )
        if not text.strip():
            raise LLMError(f"Gemini returned an empty response (finishReason={finish})")
        return text


def get_chat(settings: Settings) -> Chat:
    if not settings.llm_enabled:
        raise LLMError("Summarization is disabled (LLM_ENABLED=false)")
    if settings.llm_provider == "anthropic":
        return AnthropicChat(settings)
    if settings.llm_provider == "gemini":
        return GeminiChat(settings)
    return DeepSeekChat(settings)
