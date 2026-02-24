"""Minimal Ollama client for local LLM inference."""
from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)


class OllamaClient:
    """Simple Ollama API client for chat completions."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "jamba2-3b-q6k",
        timeout_seconds: int = 60,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout_seconds

    def chat(
        self,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
    ) -> str:
        """Send chat completion request to Ollama.

        Args:
            messages: List of message dicts with "role" and "content" keys.
            options: Optional Ollama generation options (temperature, top_p, etc.).

        Returns:
            Content string from the response.

        Raises:
            requests.HTTPError: On HTTP errors.
            requests.RequestException: On network errors.
        """
        url = f"{self.base_url}/api/chat"
        default_options = {
            "temperature": 0.4,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "num_ctx": 4096,
            "num_predict": 900,
        }
        if options:
            default_options.update(options)

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": default_options,
        }

        try:
            response = requests.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            content = data.get("message", {}).get("content", "")
            if not content:
                raise ValueError("Ollama response missing content")
            return content.strip()
        except requests.RequestException as e:
            logger.error(f"Ollama request failed: {e}")
            raise
