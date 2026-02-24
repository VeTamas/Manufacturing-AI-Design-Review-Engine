"""Shared LLM wrapper: ChatOpenAI without temperature in the request payload.

Some OpenAI models (e.g. reasoning models) only support default behavior and reject
explicit temperature. This wrapper omits temperature from both init kwargs and the
request params entirely.
"""
from __future__ import annotations

from typing import Any, Dict

from langchain_openai import ChatOpenAI


class ChatOpenAINoTemperature(ChatOpenAI):
    """ChatOpenAI that does not send temperature in the API request (model default only)."""

    def __init__(self, **kwargs: Any):
        # Defensive: drop temperature if any caller sets it
        kwargs.pop("temperature", None)
        super().__init__(**kwargs)

    @property
    def _default_params(self) -> Dict[str, Any]:
        params = super()._default_params
        params.pop("temperature", None)
        return params


def make_llm(**kwargs: Any) -> ChatOpenAINoTemperature:
    """Single factory used by all nodes. Guarantees no temperature is passed."""
    kwargs.pop("temperature", None)
    return ChatOpenAINoTemperature(**kwargs)
