"""A stand-in for the Ollama client, so lab tests need no running daemon."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class FakeOllamaClient:
    """Returns canned responses and records every call it was given."""

    def __init__(self, responses: list[str] | Callable[[dict[str, Any]], str]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    def generate(self, **kwargs: Any):
        self.calls.append(kwargs)
        if callable(self._responses):
            text = self._responses(kwargs)
        elif self._responses:
            text = self._responses.pop(0)
        else:
            text = ""
        if isinstance(text, Exception):
            raise text
        return iter([{"response": chunk} for chunk in _split(text)])

    @property
    def prompts(self) -> list[str]:
        return [str(call.get("prompt", "")) for call in self.calls]

    @property
    def systems(self) -> list[str]:
        return [str(call.get("system", "")) for call in self.calls]


def _split(text: str, size: int = 64) -> list[str]:
    body = str(text)
    if not body:
        return []
    return [body[index : index + size] for index in range(0, len(body), size)]


class FakeSummarizer:
    """Mimics `RequirementsSummarizer` closely enough for the runner's purposes."""

    instances: list["FakeSummarizer"] = []

    def __init__(self, markdown: str = "# Notes\n\nSomething useful.", **kwargs: Any) -> None:
        self.markdown = markdown
        self.kwargs = kwargs
        self.prompt_overrides = kwargs.get("prompt_overrides") or {}
        FakeSummarizer.instances.append(self)

    def summarize(self, text: str, on_progress=None, on_chunk=None, **_: Any) -> str:
        self.source = text
        if on_progress is not None:
            on_progress(1.0, "done")
        if on_chunk is not None:
            on_chunk(self.markdown)
        return self.markdown


def fake_summarizer_factory(markdown: str = "# Notes\n\nSomething useful."):
    def factory(**kwargs: Any) -> FakeSummarizer:
        return FakeSummarizer(markdown, **kwargs)

    return factory
