"""Summarization. Text only -- audio never reaches a third party.

The orchestration function lives in `sarai.llm.summarize` and is re-exported
here as `summarize_minutes`: binding it to the name `summarize` would shadow
the submodule of the same name for anyone importing both.
"""

from sarai.llm.client import Chat, LLMError, get_chat
from sarai.llm.summarize import summarize as summarize_minutes
from sarai.llm.summarize import verify_quotes

__all__ = ["Chat", "LLMError", "get_chat", "summarize_minutes", "verify_quotes"]
