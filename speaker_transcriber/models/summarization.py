from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from speaker_transcriber.errors import ProcessingCancelled
from speaker_transcriber.models.notes_assembly import (
    assemble_notes,
    fit_titles,
    recent_lines,
    topic_titles,
)
from speaker_transcriber.models.section_filter import (
    move_sections_to_end,
    strip_excluded_sections,
)
from speaker_transcriber.prompts import (
    DEFAULT_STYLE,
    MEETING_PIPELINE,
    SEGMENT_NOTES_SECTION_ID,
    SEQUENTIAL_PIPELINE,
    SummaryStyle,
    excluded_section_headings,
    get_prompt,
    get_style,
    normalize_excluded_sections,
)


LOGGER = logging.getLogger("speaker_transcriber.summarization")

CHARS_PER_TOKEN = 4
EXTRACT_PREDICT_FRACTION = 0.35
FRONT_MATTER_PREDICT_FRACTION = 0.30
DOCUMENT_PREDICT_FRACTION = 0.70
CHUNK_BUDGET_FRACTION = 0.60
STATE_CARD_FRACTION = 0.18
PROMPT_OVERHEAD_FRACTION = 0.08
MIN_CHUNK_FRACTION = 0.25
MIN_PREDICT_TOKENS = 128
MAX_CONTINUE_PASSES = 2
TRUNCATION_CAP_RATIO = 0.90

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_OOM_PATTERN = re.compile(
    r"out of memory"
    r"|\boom\b"
    r"|cuda (?:error|failure)"
    r"|kv ?cache"
    r"|requires more (?:system |gpu |video )?memory"
    r"|(?:not enough|insufficient|no available) (?:system |gpu |video |device )?memory"
    r"|(?:failed|unable) to allocate"
    r"|cannot allocate memory"
    r"|memory allocation (?:failed|error)"
    r"|model requires more",
    re.IGNORECASE,
)


class OllamaOutOfMemoryError(RuntimeError):
    """Raised when Ollama cannot fit the request in GPU (or system) memory."""


def is_out_of_memory_error(error: object) -> bool:
    text = str(error or "").strip()
    if not text:
        return False
    return _OOM_PATTERN.search(text) is not None


@dataclass
class SummarizationProgress:
    fraction: float
    message: str


@dataclass(frozen=True)
class OllamaModelInfo:
    name: str
    size_bytes: int | None = None
    max_context: int | None = None

    @property
    def approx_vram_label(self) -> str:
        return format_approx_vram(self.size_bytes)


def format_approx_vram(size_bytes: int | None) -> str:
    if size_bytes is None or size_bytes <= 0:
        return "—"
    gib = size_bytes / (1024**3)
    if gib < 0.1:
        return f"~{size_bytes / (1024**2):.0f} MB"
    return f"~{gib:.1f} GB"


def extract_generate_chunk_parts(chunk: object) -> tuple[str, str]:
    response = getattr(chunk, "response", None)
    thinking = getattr(chunk, "thinking", None)
    if response is None and isinstance(chunk, dict):
        response = chunk.get("response")
        thinking = chunk.get("thinking")
    return str(response or ""), str(thinking or "")


def extract_context_length(info: object) -> int | None:
    modelinfo = getattr(info, "modelinfo", None) or getattr(info, "model_info", None)
    if modelinfo is None and isinstance(info, dict):
        modelinfo = info.get("modelinfo") or info.get("model_info")
    if isinstance(modelinfo, dict):
        for key, value in modelinfo.items():
            if str(key).endswith("context_length"):
                try:
                    parsed = int(value)
                except (TypeError, ValueError):
                    continue
                if parsed > 0:
                    return parsed
    parameters = getattr(info, "parameters", None)
    if parameters is None and isinstance(info, dict):
        parameters = info.get("parameters")
    if isinstance(parameters, str):
        for line in parameters.splitlines():
            lowered = line.lower()
            if "num_ctx" not in lowered and "context" not in lowered:
                continue
            parts = line.split()
            if not parts:
                continue
            try:
                parsed = int(parts[-1])
            except ValueError:
                continue
            if parsed > 0:
                return parsed
    return None


class RequirementsSummarizer:
    MODEL_NAME = "qwen3.5:9b"
    CHUNK_STAGE_END = 0.55
    MERGE_STAGE_END = 0.80
    SECTION_AWARE_STAGES = frozenset({"merge", "validate", "format"})
    style: SummaryStyle = get_style(DEFAULT_STYLE)
    excluded_sections: tuple[str, ...] = ()

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        *,
        num_ctx: int,
        style: str = DEFAULT_STYLE,
        excluded_sections: tuple[str, ...] = (),
        cancel_event: threading.Event | None = None,
    ) -> None:
        """num_ctx is required: it is the Notes context length the user selected."""
        import ollama

        if int(num_ctx) <= 0:
            raise ValueError("A positive Notes context length (num_ctx) is required.")
        self.model_name = model_name
        self.num_ctx = int(num_ctx)
        self.style: SummaryStyle = get_style(style)
        self.excluded_sections = normalize_excluded_sections(style, excluded_sections)
        self.cancel_event = cancel_event
        self.client = ollama.Client()

    @property
    def style_id(self) -> str:
        return self.style.style_id

    def _excluded_headings(self) -> tuple[str, ...]:
        return excluded_section_headings(self.style_id, self.excluded_sections)

    def _segment_notes_excluded(self) -> bool:
        return SEGMENT_NOTES_SECTION_ID in self.excluded_sections

    def _exclusion_directive(self) -> str:
        """An override block appended to the document-shaping stage prompts."""
        headings = self._excluded_headings()
        skip_notes = self._segment_notes_excluded()
        if not headings and not skip_notes:
            return ""
        sentences: list[str] = []
        if headings:
            listed = ", ".join(f"`## {heading}`" for heading in headings)
            sentences.append(
                f"Leave these sections out of the document entirely: {listed}. "
                "This overrides any instruction above that asks for them: do "
                "not write the heading or its content, do not add a "
                "replacement section, and do not mention the omission."
            )
        if skip_notes:
            sentences.append(
                "The detailed per-topic discussion notes are also turned off: "
                "do not write per-topic discussion sections after the "
                "overview."
            )
        sentences.append("Produce every other section exactly as instructed.")
        return "## Sections turned off by the user\n\n" + " ".join(sentences)

    def _prompt(self, name: str) -> str:
        text = get_prompt(name, self.style_id)
        if name in self.SECTION_AWARE_STAGES:
            directive = self._exclusion_directive()
            if directive:
                return f"{text}\n\n{directive}"
        return text

    def _strip_excluded(self, markdown: str) -> str:
        """Guarantee excluded sections are gone, whatever the model produced."""
        headings = self._excluded_headings()
        if not headings:
            return markdown
        return strip_excluded_sections(markdown, headings)

    @property
    def _overview_label(self) -> str:
        return "meeting overview" if self.style.is_meeting_family else "document"

    def _raise_if_cancelled(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise ProcessingCancelled()

    @property
    def CHUNK_CHARACTER_LIMIT(self) -> int:
        return self._chunk_char_limit()

    def _num_predict(self, stage: str = "extract") -> int:
        fractions = {
            "extract": EXTRACT_PREDICT_FRACTION,
            "merge": FRONT_MATTER_PREDICT_FRACTION,
            "validate": FRONT_MATTER_PREDICT_FRACTION,
            "format": DOCUMENT_PREDICT_FRACTION,
            "continue": DOCUMENT_PREDICT_FRACTION,
        }
        fraction = fractions.get(stage, EXTRACT_PREDICT_FRACTION)
        return max(MIN_PREDICT_TOKENS, int(self.num_ctx * fraction))

    def _prompt_char_budget(self, stage: str = "extract") -> int:
        remaining_tokens = max(
            int(self.num_ctx * 0.1),
            self.num_ctx - self._num_predict(stage),
        )
        return max(CHARS_PER_TOKEN * MIN_PREDICT_TOKENS, remaining_tokens * CHARS_PER_TOKEN)

    def _prompt_overhead_chars(self) -> int:
        return int(self._prompt_char_budget("extract") * PROMPT_OVERHEAD_FRACTION)

    def _state_card_budget(self) -> int:
        budget = self._prompt_char_budget("extract")
        return max(200, int(budget * STATE_CARD_FRACTION))

    def _chunk_char_limit(self) -> int:
        budget = self._prompt_char_budget("extract")
        reserved = self._state_card_budget() + self._prompt_overhead_chars()
        sized = int(min(budget * CHUNK_BUDGET_FRACTION, budget - reserved))
        return max(int(budget * MIN_CHUNK_FRACTION), sized)

    def _running_char_budget(self) -> int:
        remaining = (
            self._prompt_char_budget("extract")
            - self._chunk_char_limit()
            - self._prompt_overhead_chars()
        )
        return max(200, min(self._state_card_budget(), remaining))

    @staticmethod
    def _model_size_bytes(item: object) -> int | None:
        size = getattr(item, "size", None)
        if size is None and isinstance(item, dict):
            size = item.get("size")
        if size is None:
            return None
        return int(size)

    @staticmethod
    def _model_name(item: object) -> str | None:
        name = getattr(item, "model", None)
        if name is None and isinstance(item, dict):
            name = item.get("model") or item.get("name")
        if not name:
            return None
        return str(name)

    @staticmethod
    def list_available_models() -> list[OllamaModelInfo]:
        import ollama

        response = ollama.Client().list()
        models = getattr(response, "models", None)
        if models is None and isinstance(response, dict):
            models = response.get("models", [])
        entries: dict[str, OllamaModelInfo] = {}
        for item in models or []:
            name = RequirementsSummarizer._model_name(item)
            if not name:
                continue
            entries[name] = OllamaModelInfo(
                name=name,
                size_bytes=RequirementsSummarizer._model_size_bytes(item),
            )
        return sorted(entries.values(), key=lambda model: model.name.lower())

    @staticmethod
    def model_max_context(model_name: str) -> int | None:
        try:
            import ollama

            info = ollama.Client().show(model_name)
        except Exception:
            LOGGER.debug("Could not read context length for %s", model_name, exc_info=True)
            return None
        return extract_context_length(info)

    def _split_oversized_paragraph(self, paragraph: str) -> list[str]:
        limit = self._chunk_char_limit()
        if len(paragraph) <= limit:
            return [paragraph]
        sentences = [part.strip() for part in _SENTENCE_SPLIT.split(paragraph) if part.strip()]
        if not sentences:
            sentences = [paragraph]
        pieces: list[str] = []
        current: list[str] = []
        for sentence in sentences:
            if len(sentence) > limit:
                if current:
                    pieces.append(" ".join(current))
                    current = []
                for start in range(0, len(sentence), limit):
                    pieces.append(sentence[start : start + limit])
                continue
            candidate = " ".join(current + [sentence])
            if current and len(candidate) > limit:
                pieces.append(" ".join(current))
                current = [sentence]
            else:
                current.append(sentence)
        if current:
            pieces.append(" ".join(current))
        return pieces or [paragraph]

    def _chunks(self, text: str) -> list[str]:
        limit = self._chunk_char_limit()
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        units: list[str] = []
        for paragraph in paragraphs:
            units.extend(self._split_oversized_paragraph(paragraph))
        chunks: list[str] = []
        current: list[str] = []
        for unit in units:
            candidate = "\n\n".join(current + [unit])
            if current and len(candidate) > limit:
                chunks.append("\n\n".join(current))
                current = [unit]
            else:
                current.append(unit)
        if current:
            chunks.append("\n\n".join(current))
        return chunks or [text.strip()]

    def _generate_stream(
        self,
        prompt: str,
        token_limit: int | None = None,
        on_chunk: Callable[[str], None] | None = None,
        on_reasoning: Callable[[int], None] | None = None,
    ) -> str:
        limit = token_limit if token_limit is not None else self._num_predict("extract")
        generate_kwargs = {
            "model": self.model_name,
            "system": self._prompt("system"),
            "prompt": prompt,
            "stream": True,
            "think": False,
            "options": {
                "num_predict": limit,
                "num_ctx": self.num_ctx,
                "temperature": 0.2,
            },
        }
        response_parts: list[str] = []
        thinking_parts: list[str] = []
        stream = None
        try:
            self._raise_if_cancelled()
            try:
                stream = self.client.generate(**generate_kwargs)
            except TypeError:
                generate_kwargs.pop("think", None)
                stream = self.client.generate(**generate_kwargs)
            for chunk in stream:
                self._raise_if_cancelled()
                response, thinking = extract_generate_chunk_parts(chunk)
                if thinking:
                    thinking_parts.append(thinking)
                    if on_reasoning is not None and not response_parts:
                        on_reasoning(sum(len(part) for part in thinking_parts))
                    if on_chunk is not None and not response_parts:
                        on_chunk(thinking)
                if response:
                    response_parts.append(response)
                    if on_chunk is not None:
                        on_chunk(response)
        except OllamaOutOfMemoryError:
            raise
        except ProcessingCancelled:
            raise
        except Exception as exc:
            if is_out_of_memory_error(exc):
                LOGGER.warning(
                    "Ollama ran out of memory (model=%s, num_ctx=%d, num_predict=%d): %s",
                    self.model_name,
                    self.num_ctx,
                    limit,
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
        full_response = "".join(response_parts).strip()
        if full_response:
            return full_response
        return "".join(thinking_parts).strip()

    def _pack_groups(
        self,
        sections: list[str],
        instruction: str,
        stage: str = "merge",
    ) -> list[list[str]]:
        budget = self._prompt_char_budget(stage) - len(instruction) - 200
        budget = max(1000, budget)
        groups: list[list[str]] = []
        current: list[str] = []
        current_len = 0
        for section in sections:
            extra = len(section) + 40
            if current and current_len + extra > budget:
                groups.append(current)
                current = [section]
                current_len = extra
            else:
                current.append(section)
                current_len += extra
        if current:
            groups.append(current)
        return groups

    def _looks_truncated(
        self,
        text: str,
        token_limit: int,
        require_sections: bool = False,
    ) -> bool:
        stripped = text.rstrip()
        if not stripped:
            return False
        cap = token_limit * CHARS_PER_TOKEN
        if len(stripped) < int(cap * TRUNCATION_CAP_RATIO):
            return False
        last = stripped[-1]
        ends_incomplete = last not in ".!?:\"'` \n"
        if ends_incomplete:
            return True
        if not require_sections:
            return False
        required = self._required_sections()
        if not required:
            return False
        lower = stripped.lower()
        return not any(section in lower for section in required)

    def _required_sections(self) -> tuple[str, ...]:
        """The style's required phrases, minus those the user turned off."""
        required = self.style.required_sections
        if not required or not self.excluded_sections:
            return required
        excluded = [heading.casefold() for heading in self._excluded_headings()]
        return tuple(
            phrase
            for phrase in required
            if not any(phrase in heading for heading in excluded)
        )

    def _join_continuation(self, prefix: str, addition: str) -> str:
        left = prefix.rstrip()
        right = addition.strip()
        if not right:
            return left
        if left.endswith((".", "!", "?", ":", "|", "-", "*")) or right.startswith("#"):
            return f"{left}\n\n{right}"
        return f"{left} {right}"

    def _continuation_prompt(self, document: str, stage: str) -> str:
        instruction = get_prompt("continue")
        budget = max(500, self._prompt_char_budget(stage) - len(instruction) - 80)
        if len(document) <= budget:
            body = document
            note = ""
        else:
            body = document[-budget:]
            note = "\n\n(Earlier pages omitted; continue from the end of this excerpt.)\n"
        return f"{instruction}{note}\n\n## Document so far\n\n{body}"

    def _ensure_complete(
        self,
        text: str,
        stage: str,
        on_chunk: Callable[[str], None] | None = None,
        on_reasoning: Callable[[int], None] | None = None,
        require_sections: bool = False,
    ) -> str:
        token_limit = self._num_predict(stage)
        continued = text
        for pass_index in range(MAX_CONTINUE_PASSES):
            self._raise_if_cancelled()
            if not self._looks_truncated(continued, token_limit, require_sections):
                return continued
            LOGGER.info(
                "Output looks truncated (%d characters, num_predict=%d); "
                "continuing generation pass %d",
                len(continued),
                token_limit,
                pass_index + 1,
            )
            started = time.monotonic()
            addition = self._generate_stream(
                self._continuation_prompt(continued, stage),
                token_limit,
                on_chunk,
                on_reasoning,
            )
            LOGGER.info(
                "Continuation pass %d complete in %.1f seconds (%d characters)",
                pass_index + 1,
                time.monotonic() - started,
                len(addition),
            )
            if not addition.strip():
                break
            continued = self._join_continuation(continued, addition)
        return continued

    def _merge(
        self,
        sections: list[str],
        on_chunk: Callable[[str], None] | None = None,
        on_reasoning: Callable[[int], None] | None = None,
    ) -> str:
        instruction = self._prompt("merge")
        merged = "\n\n".join(
            f"### Section {index}\n\n{section}"
            for index, section in enumerate(sections, start=1)
        )
        token_limit = self._num_predict("merge")
        LOGGER.info(
            "Merging %d section(s) (num_predict=%d, prompt=%d characters)",
            len(sections),
            token_limit,
            len(instruction) + len(merged),
        )
        started = time.monotonic()
        result = self._generate_stream(
            f"{instruction}\n\n{merged}",
            token_limit,
            on_chunk,
            on_reasoning,
        )
        result = self._ensure_complete(
            result,
            "merge",
            on_chunk,
            on_reasoning,
            require_sections=True,
        )
        LOGGER.info(
            "Merge complete in %.1f seconds (%d characters)",
            time.monotonic() - started,
            len(result),
        )
        return result

    def _assemble_document(self, front_matter: str, extracts: list[str]) -> str:
        """Join the generated overview with one merged body of section notes.

        Only the meeting styles keep the segment notes: every other style's
        merge pass already wrote the whole document. When the user turned the
        detailed notes off, the overview is the document. Trailing sections —
        a meeting's Closing Assessment — are moved behind the appended notes
        so they end the document.
        """
        if self.style.pipeline != MEETING_PIPELINE:
            return front_matter.strip()
        if self._segment_notes_excluded():
            document = front_matter.strip()
        else:
            document = assemble_notes(front_matter, extracts)
        return move_sections_to_end(document, self.style.trailing_sections)

    def _running_outline(self, extracts: list[str]) -> str:
        """Background for the next segment: topics so far, plus the latest notes.

        This is deliberately not the earlier extracts themselves. Handing the
        model back its own Participants, Decisions, and Action items blocks is
        what made it copy them into every segment.
        """
        if not extracts or not self.style.uses_running_outline:
            return ""
        budget = self._running_char_budget()
        parts: list[str] = []
        titles = topic_titles(extracts)
        if titles:
            parts.append(
                "Topics already recorded: " + fit_titles(titles, int(budget * 0.5))
            )
        used = sum(len(part) + 2 for part in parts)
        tail = recent_lines(extracts[-1], max(0, budget - used - 40))
        if tail:
            parts.append("Where the previous segment left off:\n" + tail)
        outline = "\n\n".join(parts).strip()
        return outline[:budget].rstrip() if len(outline) > budget else outline

    def _chunk_prompt(self, chunk: str, running: str, is_last: bool) -> str:
        marker = "[END OF TRANSCRIPT]" if is_last else "[MORE SEGMENTS FOLLOW]"
        parts = [self._prompt("chunk")]
        if running:
            parts.append(
                "## Already recorded, background only\n\n"
                "Do not repeat any of this. Write notes only for what is new in "
                "the segment below.\n\n" + running
            )
            parts.append(
                "## New transcript segment (this is a continuation, not the end "
                "unless marked END OF TRANSCRIPT)\n\n" + chunk
            )
        else:
            parts.append("## Transcript segment\n\n" + chunk)
        parts.append(marker)
        return "\n\n".join(parts)

    def _format_extracts(self, extracts: list[str], start_index: int = 1) -> str:
        return "\n\n".join(
            f"### Extract {index}\n\n{extract}"
            for index, extract in enumerate(extracts, start=start_index)
        )

    def _validate(
        self,
        draft: str,
        extracts: list[str],
        on_progress: Callable[[float, str], None] | None,
        on_chunk: Callable[[str], None] | None,
        on_section_break: Callable[[], None] | None,
        on_reasoning: Callable[[int], None] | None,
        stage_start: float,
    ) -> str:
        instruction = self._prompt("validate")
        token_limit = self._num_predict("validate")
        budget = self._prompt_char_budget("validate")
        packed = self._format_extracts(extracts)
        combined_len = len(instruction) + len(draft) + len(packed) + 80

        def emit(fraction: float, message: str) -> None:
            if on_progress is not None:
                on_progress(min(max(fraction, 0.0), 0.99), message)

        if combined_len > budget:
            LOGGER.info(
                "Skipping validation: draft plus %d extract(s) need %d characters "
                "but only %d fit in the context window",
                len(extracts),
                combined_len,
                budget,
            )
            return draft

        emit(stage_start, f"Checking the {self._overview_label} against section notes…")
        if on_section_break is not None:
            on_section_break()
        LOGGER.info(
            "Validating front matter in one pass (num_predict=%d, prompt=%d characters)",
            token_limit,
            combined_len,
        )
        started = time.monotonic()
        validated = self._generate_stream(
            f"{instruction}\n\n## Draft summary\n\n{draft}\n\n"
            f"## Section extracts\n\n{packed}",
            token_limit,
            on_chunk,
            on_reasoning,
        )
        if not validated.strip():
            LOGGER.warning("Validation returned nothing; keeping the merged draft")
            return draft
        if len(validated.strip()) < int(len(draft.strip()) * 0.6):
            LOGGER.warning(
                "Validation shortened the overview from %d to %d characters; "
                "keeping the merged draft",
                len(draft.strip()),
                len(validated.strip()),
            )
            return draft
        validated = self._ensure_complete(
            validated,
            "validate",
            on_chunk,
            on_reasoning,
            require_sections=True,
        )
        LOGGER.info(
            "Validation complete in %.1f seconds (%d characters)",
            time.monotonic() - started,
            len(validated),
        )
        return validated

    def format_meeting_notes(
        self,
        markdown: str,
        on_progress: Callable[[float, str], None] | None = None,
        on_chunk: Callable[[str], None] | None = None,
    ) -> str:
        if not markdown.strip():
            raise ValueError("The meeting notes are empty.")
        self._raise_if_cancelled()
        if on_progress is not None:
            on_progress(0.0, "Formatting meeting notes…")
        token_limit = self._num_predict("format")
        LOGGER.info("Formatting meeting notes (num_predict=%d)", token_limit)
        formatted = self._generate_stream(
            f"{self._prompt('format')}\n\n{markdown.strip()}",
            token_limit,
            on_chunk,
        )
        if not formatted.strip():
            raise RuntimeError("Ollama returned empty formatted meeting notes.")
        formatted = self._ensure_complete(formatted, "format", on_chunk)
        formatted = self._strip_excluded(formatted)
        formatted = move_sections_to_end(formatted, self.style.trailing_sections)
        if on_progress is not None:
            on_progress(1.0, "Formatting complete")
        return formatted

    def summarize(
        self,
        text: str,
        on_progress: Callable[[float, str], None] | None = None,
        on_chunk: Callable[[str], None] | None = None,
        on_section_break: Callable[[], None] | None = None,
    ) -> str:
        if not text.strip():
            raise ValueError("The transcript is empty.")
        try:
            chunks = self._chunks(text)
            LOGGER.info(
                "Starting %s summarization with %s (num_ctx=%d, extract_predict=%d, "
                "merge_predict=%d, document_predict=%d, chunk_limit=%d, %d chunk(s))",
                self.style_id,
                self.model_name,
                self.num_ctx,
                self._num_predict("extract"),
                self._num_predict("merge"),
                self._num_predict("validate"),
                self._chunk_char_limit(),
                len(chunks),
            )

            def emit_progress(fraction: float, message: str) -> None:
                if on_progress is None:
                    return
                on_progress(min(max(fraction, 0.0), 1.0), message)

            def on_reasoning(char_count: int) -> None:
                emit_progress(
                    getattr(on_reasoning, "fraction", 0.0),
                    f"Model reasoning… ({char_count:,} characters)",
                )

            extracts: list[str] = []
            running = ""
            total_chunks = len(chunks)
            for index, chunk in enumerate(chunks, start=1):
                self._raise_if_cancelled()
                is_last = index == total_chunks
                fraction = self.CHUNK_STAGE_END * ((index - 1) / total_chunks)
                emit_progress(
                    fraction,
                    f"Summarizing section {index} of {total_chunks}…",
                )
                on_reasoning.fraction = fraction
                LOGGER.info("Summarizing section %d of %d", index, total_chunks)
                if index > 1 and on_section_break is not None:
                    on_section_break()
                started = time.monotonic()
                section_summary = self._generate_stream(
                    self._chunk_prompt(chunk, running, is_last),
                    self._num_predict("extract"),
                    on_chunk,
                    on_reasoning,
                )
                LOGGER.info(
                    "Completed section %d of %d in %.1f seconds (%d characters)",
                    index,
                    total_chunks,
                    time.monotonic() - started,
                    len(section_summary),
                )
                if not section_summary.strip():
                    raise RuntimeError(
                        f"Ollama returned an empty summary for section {index}."
                    )
                section_summary = self._ensure_complete(
                    section_summary,
                    "extract",
                    on_chunk,
                    on_reasoning,
                )
                extracts.append(section_summary)
                if not is_last:
                    running = self._running_outline(extracts)
                emit_progress(
                    self.CHUNK_STAGE_END * (index / total_chunks),
                    f"Completed section {index} of {total_chunks}",
                )

            if self.style.pipeline == SEQUENTIAL_PIPELINE:
                summary = self._strip_excluded(
                    "\n\n".join(
                        extract.strip() for extract in extracts if extract.strip()
                    )
                )
                emit_progress(1.0, "Summary complete")
                LOGGER.info(
                    "Summarization complete (%d characters from %d segment(s))",
                    len(summary),
                    len(extracts),
                )
                return summary

            front_matter = self._front_matter(
                extracts,
                emit_progress,
                on_chunk,
                on_section_break,
                on_reasoning,
            )
            front_matter = self._validate(
                front_matter,
                extracts,
                emit_progress,
                on_chunk,
                on_section_break,
                on_reasoning,
                self.MERGE_STAGE_END,
            )
            summary = self._strip_excluded(
                self._assemble_document(front_matter, extracts)
            )
            emit_progress(1.0, "Summary complete")
            LOGGER.info(
                "Summarization complete (%d characters from %d extract(s), "
                "%d characters of overview)",
                len(summary),
                len(extracts),
                len(front_matter),
            )
            return summary
        except OllamaOutOfMemoryError:
            raise
        except ProcessingCancelled:
            raise
        except Exception:
            LOGGER.exception(
                "Local summarization failed. Ensure Ollama is running and model %s is installed.",
                self.model_name,
            )
            raise RuntimeError(
                f"Could not summarize locally. Ensure Ollama is running and "
                f"`ollama pull {self.model_name}` has completed."
            )

    def _front_matter(
        self,
        extracts: list[str],
        emit_progress: Callable[[float, str], None],
        on_chunk: Callable[[str], None] | None,
        on_section_break: Callable[[], None] | None,
        on_reasoning: Callable[[int], None] | None,
    ) -> str:
        """Write the overview sections. The extract list itself is never reduced."""
        if not extracts:
            return ""
        if len(extracts) == 1:
            emit_progress(self.CHUNK_STAGE_END, f"Writing the {self._overview_label}…")
            if on_section_break is not None:
                on_section_break()
            return self._merge(extracts, on_chunk, on_reasoning)

        sections = list(extracts)
        merge_round = 1
        progress_span = self.MERGE_STAGE_END - self.CHUNK_STAGE_END
        while len(sections) > 1:
            instruction = self._prompt("merge")
            groups = self._pack_groups(sections, instruction, stage="merge")
            if all(len(group) == 1 for group in groups) and len(sections) > 1:
                groups = [
                    sections[index : index + 2]
                    for index in range(0, len(sections), 2)
                ]
            LOGGER.info(
                "Overview round %d: %d section(s) in %d batch(es)",
                merge_round,
                len(sections),
                len(groups),
            )
            next_sections: list[str] = []
            for batch_number, batch in enumerate(groups, start=1):
                self._raise_if_cancelled()
                fraction = self.CHUNK_STAGE_END + progress_span * (
                    (batch_number - 1) / max(len(groups), 1)
                )
                if len(batch) == 1:
                    next_sections.append(batch[0])
                    continue
                emit_progress(
                    fraction,
                    f"Writing the {self._overview_label} (round {merge_round}, "
                    f"batch {batch_number} of {len(groups)})…",
                )
                if on_reasoning is not None:
                    on_reasoning.fraction = fraction
                if on_section_break is not None:
                    on_section_break()
                merged_summary = self._merge(batch, on_chunk, on_reasoning)
                if not merged_summary.strip():
                    raise RuntimeError(
                        f"Ollama returned an empty {self._overview_label} in "
                        f"round {merge_round}."
                    )
                next_sections.append(merged_summary)
                emit_progress(
                    self.CHUNK_STAGE_END
                    + progress_span * (batch_number / max(len(groups), 1)),
                    f"Completed batch {batch_number} of {len(groups)}",
                )
            if next_sections == sections:
                LOGGER.warning(
                    "Overview packing could not reduce %d section(s); using the first.",
                    len(sections),
                )
                sections = [sections[0]]
                break
            sections = next_sections
            merge_round += 1
        return sections[0]
