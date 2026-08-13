from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from speaker_transcriber.prompts import get_prompt


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

DETAIL_SECTION_TITLE = "Detailed Notes"

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_KEEP_PARAGRAPH = re.compile(
    r"(participant|decision|action|risk|question|blocker|dependenc|"
    r"deadline|speaker_|owner|\*\*|^\s*\|)",
    re.IGNORECASE | re.MULTILINE,
)
_REQUIRED_SECTIONS = ("action items", "open questions")
_ANY_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_BOLD_ONLY_LINE = re.compile(r"^\s{0,3}(?:\*\*|__)(.+?)(?:\*\*|__)\s*:?\s*$")
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

    def __init__(
        self,
        model_name: str = MODEL_NAME,
        *,
        num_ctx: int,
    ) -> None:
        """num_ctx is required: it is the Notes context length the user selected."""
        import ollama

        if int(num_ctx) <= 0:
            raise ValueError("A positive Notes context length (num_ctx) is required.")
        self.model_name = model_name
        self.num_ctx = int(num_ctx)
        self.client = ollama.Client()

    @property
    def CHUNK_CHARACTER_LIMIT(self) -> int:
        return self._chunk_char_limit()

    def _num_predict(self, stage: str = "extract") -> int:
        fractions = {
            "extract": EXTRACT_PREDICT_FRACTION,
            "compact": EXTRACT_PREDICT_FRACTION,
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

    def _compact_char_budget(self) -> int:
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
            "system": get_prompt("system"),
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
        try:
            try:
                stream = self.client.generate(**generate_kwargs)
            except TypeError:
                generate_kwargs.pop("think", None)
                stream = self.client.generate(**generate_kwargs)
            for chunk in stream:
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
        lower = stripped.lower()
        return not any(section in lower for section in _REQUIRED_SECTIONS)

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

    def _extractive_trim(self, text: str, budget: int, hard: bool = True) -> str:
        stripped = text.strip()
        if len(stripped) <= budget:
            return stripped
        paragraphs = [part.strip() for part in stripped.split("\n\n") if part.strip()]
        kept = [part for part in paragraphs if _KEEP_PARAGRAPH.search(part)]
        candidate = "\n\n".join(kept) if kept else stripped
        if len(candidate) <= budget:
            return candidate
        if not hard:
            return candidate
        return candidate[-budget:].lstrip()

    def _merge(
        self,
        sections: list[str],
        on_chunk: Callable[[str], None] | None = None,
        on_reasoning: Callable[[int], None] | None = None,
    ) -> str:
        instruction = get_prompt("merge")
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

    def _normalize_extract_body(self, extract: str) -> str:
        """Demote extract headings so stitched notes cannot split the document."""
        lines: list[str] = []
        for line in extract.strip().splitlines():
            heading = _ANY_HEADING.match(line)
            if heading is not None:
                title = heading.group(1).strip()
                lines.append(f"### {title}" if title else "")
                continue
            bold = _BOLD_ONLY_LINE.match(line)
            if bold is not None:
                lines.append(f"### {bold.group(1).strip()}")
                continue
            lines.append(line)
        return "\n".join(lines).strip()

    def _assemble_document(self, front_matter: str, extracts: list[str]) -> str:
        """Join the generated overview with the verbatim section notes."""
        parts = [front_matter.strip()]
        total = len(extracts)
        for index, extract in enumerate(extracts, start=1):
            body = self._normalize_extract_body(extract)
            if not body:
                continue
            if total > 1:
                heading = f"## {DETAIL_SECTION_TITLE} — Part {index} of {total}"
            else:
                heading = f"## {DETAIL_SECTION_TITLE}"
            parts.append(f"{heading}\n\n{body}")
        return "\n\n".join(part for part in parts if part).strip()

    def _compact_running(
        self,
        running: str,
        addition: str = "",
        on_chunk: Callable[[str], None] | None = None,
        on_reasoning: Callable[[int], None] | None = None,
    ) -> str:
        combined = running.strip()
        extra = addition.strip()
        if extra:
            combined = f"{combined}\n\n{extra}".strip() if combined else extra
        budget = self._compact_char_budget()
        if len(combined) <= budget:
            return combined
        trimmed = self._extractive_trim(combined, budget, hard=False)
        if len(trimmed) <= budget:
            LOGGER.info(
                "Trimmed running context extractively from %d to %d characters",
                len(combined),
                len(trimmed),
            )
            return trimmed
        LOGGER.info(
            "Compacting running context with model (%d characters, budget %d)",
            len(combined),
            budget,
        )
        started = time.monotonic()
        compacted = self._generate_stream(
            f"{get_prompt('compact')}\n\n{combined}",
            self._num_predict("compact"),
            on_chunk,
            on_reasoning,
        ).strip()
        LOGGER.info(
            "Compact complete in %.1f seconds (%d characters)",
            time.monotonic() - started,
            len(compacted),
        )
        if compacted and len(compacted) <= budget:
            return compacted
        return self._extractive_trim(compacted or combined, budget)

    def _chunk_prompt(self, chunk: str, running: str, is_last: bool) -> str:
        marker = "[END OF TRANSCRIPT]" if is_last else "[MORE SEGMENTS FOLLOW]"
        parts = [get_prompt("chunk")]
        if running:
            parts.append("## Context from earlier in this meeting\n\n" + running)
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
        instruction = get_prompt("validate")
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

        emit(stage_start, "Checking the overview against section notes…")
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
        if on_progress is not None:
            on_progress(0.0, "Formatting meeting notes…")
        token_limit = self._num_predict("format")
        LOGGER.info("Formatting meeting notes (num_predict=%d)", token_limit)
        formatted = self._generate_stream(
            f"{get_prompt('format')}\n\n{markdown.strip()}",
            token_limit,
            on_chunk,
        )
        if not formatted.strip():
            raise RuntimeError("Ollama returned empty formatted meeting notes.")
        formatted = self._ensure_complete(formatted, "format", on_chunk)
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
                "Starting summarization with %s (num_ctx=%d, extract_predict=%d, "
                "merge_predict=%d, document_predict=%d, chunk_limit=%d, %d chunk(s))",
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
                    running = self._compact_running(
                        running,
                        section_summary,
                        on_chunk,
                        on_reasoning,
                    )
                emit_progress(
                    self.CHUNK_STAGE_END * (index / total_chunks),
                    f"Completed section {index} of {total_chunks}",
                )

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
            summary = self._assemble_document(front_matter, extracts)
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
            emit_progress(self.CHUNK_STAGE_END, "Writing the meeting overview…")
            if on_section_break is not None:
                on_section_break()
            return self._merge(extracts, on_chunk, on_reasoning)

        sections = list(extracts)
        merge_round = 1
        progress_span = self.MERGE_STAGE_END - self.CHUNK_STAGE_END
        while len(sections) > 1:
            instruction = get_prompt("merge")
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
                fraction = self.CHUNK_STAGE_END + progress_span * (
                    (batch_number - 1) / max(len(groups), 1)
                )
                if len(batch) == 1:
                    next_sections.append(batch[0])
                    continue
                emit_progress(
                    fraction,
                    f"Writing the meeting overview (round {merge_round}, "
                    f"batch {batch_number} of {len(groups)})…",
                )
                if on_reasoning is not None:
                    on_reasoning.fraction = fraction
                if on_section_break is not None:
                    on_section_break()
                merged_summary = self._merge(batch, on_chunk, on_reasoning)
                if not merged_summary.strip():
                    raise RuntimeError(
                        f"Ollama returned an empty overview in round {merge_round}."
                    )
                next_sections.append(merged_summary)
                emit_progress(
                    self.CHUNK_STAGE_END
                    + progress_span * (batch_number / max(len(groups), 1)),
                    f"Completed overview batch {batch_number} of {len(groups)}",
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
