"""A small streaming Ollama wrapper shared by the lab's three model roles.

The summarizer under test has its own client; this one drives the generator,
judge, and optimizer. It keeps the same cancellation and out-of-memory
behaviour as `RequirementsSummarizer` so a lab batch fails the same way a real
summarization does, and it accepts an injected client so tests never need a
running daemon.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from speaker_transcriber.errors import ProcessingCancelled
from speaker_transcriber.models.summarization import (
    OllamaOutOfMemoryError,
    extract_generate_chunk_parts,
    is_out_of_memory_error,
)


LOGGER = logging.getLogger("speaker_transcriber.promptlab.ollama")

DEFAULT_NUM_CTX = 8192
DEFAULT_NUM_PREDICT = 2048


class LabOllama:
    """One model, one context length, many calls."""

    def __init__(
        self,
        model_name: str,
        *,
        num_ctx: int = DEFAULT_NUM_CTX,
        temperature: float = 0.4,
        cancel_event: threading.Event | None = None,
        client: Any = None,
    ) -> None:
        if not str(model_name or "").strip():
            raise ValueError("An Ollama model name is required.")
        if int(num_ctx) <= 0:
            raise ValueError("A positive context length is required.")
        self.model_name = str(model_name)
        self.num_ctx = int(num_ctx)
        self.temperature = float(temperature)
        self.cancel_event = cancel_event
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            import ollama

            self._client = ollama.Client()
        return self._client

    def raise_if_cancelled(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise ProcessingCancelled()

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        num_predict: int = DEFAULT_NUM_PREDICT,
        temperature: float | None = None,
        on_chunk: Callable[[str], None] | None = None,
    ) -> str:
        """The model's full response, streamed so cancellation stays responsive."""
        self.raise_if_cancelled()
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": True,
            "think": False,
            "options": {
                "num_predict": int(num_predict),
                "num_ctx": self.num_ctx,
                "temperature": (
                    self.temperature if temperature is None else float(temperature)
                ),
            },
        }
        if system.strip():
            kwargs["system"] = system

        parts: list[str] = []
        thinking: list[str] = []
        stream = None
        try:
            try:
                stream = self.client.generate(**kwargs)
            except TypeError:
                kwargs.pop("think", None)
                stream = self.client.generate(**kwargs)
            for chunk in stream:
                self.raise_if_cancelled()
                response, thought = extract_generate_chunk_parts(chunk)
                if thought:
                    thinking.append(thought)
                if response:
                    parts.append(response)
                    if on_chunk is not None:
                        on_chunk(response)
        except (OllamaOutOfMemoryError, ProcessingCancelled):
            raise
        except Exception as exc:
            if is_out_of_memory_error(exc):
                LOGGER.warning(
                    "Prompt Lab ran out of memory (model=%s, num_ctx=%d): %s",
                    self.model_name,
                    self.num_ctx,
                    exc,
                )
                raise OllamaOutOfMemoryError(str(exc)) from exc
            raise
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    LOGGER.debug("Could not close the Ollama stream", exc_info=True)

        answer = "".join(parts).strip()
        return answer or "".join(thinking).strip()
