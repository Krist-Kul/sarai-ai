"""Chat clients.

Two providers, one method. The summarizer only ever needs "here is a system
prompt and a user message, give me back text", so that is the whole interface --
map-reduce, validation and retries live in `sarai.llm.summarize` and work
identically against either provider.

Both are text-only. Audio never reaches them; that is the entire point of the
architecture and it is enforced here by there being no way to send bytes.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from sarai.config import Settings

# Non-streaming: minutes for a 90-minute meeting land well inside this, and the
# SDK's own HTTP timeout is the backstop. Anything larger would need streaming.
MAX_TOKENS = 16_000


class LLMError(RuntimeError):
    """The provider refused, failed, or returned something unusable."""


class Chat(Protocol):
    """One completion call. The model name is carried so it can be recorded
    alongside the summary -- minutes are only reproducible if you know which
    model wrote them."""

    model: str

    async def complete(self, system: str, user: str) -> str: ...


class DeepSeekChat:
    """DeepSeek's OpenAI-compatible /chat/completions endpoint."""

    def __init__(self, settings: Settings) -> None:
        if not settings.deepseek_api_key:
            raise LLMError("DEEPSEEK_API_KEY is not set")
        self.model = settings.deepseek_model
        self._key = settings.deepseek_api_key
        self._url = settings.deepseek_base_url.rstrip("/") + "/chat/completions"
        self._timeout = settings.llm_timeout_seconds

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
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                res = await client.post(
                    self._url,
                    headers={"Authorization": f"Bearer {self._key}"},
                    json=payload,
                )
            except httpx.HTTPError as exc:
                raise LLMError(f"Could not reach DeepSeek: {exc}") from exc

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


def get_chat(settings: Settings) -> Chat:
    if not settings.llm_enabled:
        raise LLMError("Summarization is disabled (LLM_ENABLED=false)")
    if settings.llm_provider == "anthropic":
        return AnthropicChat(settings)
    return DeepSeekChat(settings)
