"""Ollama client -- native /api/chat interface with think: false.

Uses the native Ollama HTTP API (NOT the OpenAI-compatible endpoint)
because the OpenAI endpoint strips thinking tokens and returns empty
content for Qwen3.5 models.

All requests send think: false to suppress chain-of-thought output.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen3.5:35b-a3b"
DEFAULT_TIMEOUT = 120.0  # seconds -- LLM inference can be slow


class OllamaClient:
    """Async client for the native Ollama /api/chat endpoint.

    Always sends think: false to prevent Qwen3.5 from emitting
    internal reasoning tokens.

    Args:
        base_url: Ollama server URL (default http://localhost:11434).
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def chat(
        self,
        model: str = DEFAULT_MODEL,
        messages: list[dict[str, str]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool = False,
        stream: bool = False,
    ) -> dict[str, Any] | AsyncIterator[dict[str, Any]]:
        """Send a chat request to Ollama.

        Args:
            model: Model name (default qwen3.5:35b-a3b).
            messages: List of {role, content} message dicts.
            options: Ollama options (temperature, num_predict, etc.).
            think: Whether to enable thinking mode (default False).
            stream: Whether to stream the response.

        Returns:
            If stream=False: complete response dict with message.content.
            If stream=True: async iterator of chunk dicts.

        Raises:
            Exception: On non-200 responses or connection errors.
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages or [],
            "think": think,
            "stream": stream,
        }

        if options:
            payload["options"] = options

        url = f"{self._base_url}/api/chat"

        if stream:
            return self._stream_chat(url, payload)
        else:
            return await self._blocking_chat(url, payload)

    async def _blocking_chat(self, url: str, payload: dict) -> dict[str, Any]:
        """Non-streaming chat request."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    async def _stream_chat(self, url: str, payload: dict) -> AsyncIterator[dict[str, Any]]:
        """Streaming chat request -- yields chunks as they arrive."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.strip():
                        try:
                            chunk = json.loads(line)
                            yield chunk
                        except json.JSONDecodeError:
                            logger.warning("Failed to parse Ollama stream chunk: %s", line[:100])

    async def health(self) -> bool:
        """Check if Ollama is reachable.

        Returns:
            True if the Ollama API responds, False otherwise.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """List available models on the Ollama server.

        Returns:
            List of model name strings.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{self._base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
