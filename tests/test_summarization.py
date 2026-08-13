import threading

import pytest

from speaker_transcriber.errors import ProcessingCancelled
from speaker_transcriber.models.summarization import (
    EXTRACT_PREDICT_FRACTION,
    FRONT_MATTER_PREDICT_FRACTION,
    DOCUMENT_PREDICT_FRACTION,
    OllamaOutOfMemoryError,
    RequirementsSummarizer,
    extract_context_length,
    is_out_of_memory_error,
)
from speaker_transcriber.prompts import (
    DEFAULT_STYLE,
    get_prompt,
    get_style,
    load_prompts,
)


FRONT_MATTER = (
    "# Weekly Sync\n\n"
    "*One line summary.*\n\n"
    "**Participants:** Alex, Jordan\n\n"
    "## Executive Summary\n\nShort overview.\n\n"
    "## Action Items\n\n"
    "| Owner | Action | Priority |\n| --- | --- | --- |\n| Alex | Ship it | High |\n\n"
    "## Open Questions\n\n- None\n"
)


class FakeChunk:
    def __init__(self, response: str = "", thinking: str = "") -> None:
        self.response = response
        self.thinking = thinking


class RecordingClient:
    def __init__(self, outputs: list[str] | None = None) -> None:
        self.outputs = list(outputs or [])
        self.calls: list[dict] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        text = self.outputs.pop(0) if self.outputs else "ok"
        yield FakeChunk(response=text)


class FailingClient:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls: list[dict] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        raise self.error
        yield  # pragma: no cover - generator marker


def make_summarizer(
    client: object,
    num_ctx: int = 8192,
    style: str = DEFAULT_STYLE,
) -> RequirementsSummarizer:
    summarizer = RequirementsSummarizer.__new__(RequirementsSummarizer)
    summarizer.model_name = "test-model"
    summarizer.num_ctx = num_ctx
    summarizer.style = get_style(style)
    summarizer.cancel_event = None
    summarizer.client = client
    return summarizer


def test_generate_stream_passes_num_ctx() -> None:
    load_prompts()
    client = RecordingClient(["Hello"])
    summarizer = make_summarizer(client, num_ctx=16384)
    result = summarizer._generate_stream("prompt", 100)
    assert result == "Hello"
    assert client.calls[0]["options"]["num_ctx"] == 16384
    assert client.calls[0]["options"]["num_predict"] == 100
    assert client.calls[0]["think"] is False
    assert "think" not in client.calls[0]["options"]


def test_num_ctx_is_required() -> None:
    with pytest.raises(TypeError):
        RequirementsSummarizer("model")  # type: ignore[call-arg]


def test_chunks_split_long_paragraph_on_sentences() -> None:
    summarizer = make_summarizer(RecordingClient(), num_ctx=2048)
    sentence = "This is a complete sentence about the meeting topic."
    paragraph = " ".join([sentence] * 120)
    assert len(paragraph) > summarizer.CHUNK_CHARACTER_LIMIT
    chunks = summarizer._chunks(paragraph)
    assert len(chunks) > 1
    assert all(len(chunk) <= summarizer.CHUNK_CHARACTER_LIMIT + len(sentence) for chunk in chunks)
    assert "".join(chunk.replace(" ", "") for chunk in chunks) == paragraph.replace(" ", "")


def test_chunk_size_grows_with_context() -> None:
    small = make_summarizer(RecordingClient(), num_ctx=2048)
    large = make_summarizer(RecordingClient(), num_ctx=8192)
    assert large.CHUNK_CHARACTER_LIMIT > 3500
    assert large.CHUNK_CHARACTER_LIMIT > small.CHUNK_CHARACTER_LIMIT
    sentence = "This is a complete sentence about the meeting topic. "
    paragraph = sentence * 400
    small_chunks = small._chunks(paragraph)
    large_chunks = large._chunks(paragraph)
    assert len(large_chunks) < len(small_chunks)
    assert len(large_chunks) >= 1


def test_budgets_scale_with_the_selected_context() -> None:
    """No fixed window: every character budget follows the Notes context slider."""
    small = make_summarizer(RecordingClient(), num_ctx=8192)
    large = make_summarizer(RecordingClient(), num_ctx=32768)
    ratio = large.num_ctx / small.num_ctx
    assert large._state_card_budget() == pytest.approx(
        small._state_card_budget() * ratio, rel=0.02
    )
    assert large._chunk_char_limit() == pytest.approx(
        small._chunk_char_limit() * ratio, rel=0.02
    )
    assert large._prompt_char_budget("extract") > small._prompt_char_budget("extract")
    assert large._running_char_budget() > small._running_char_budget()


def test_document_stages_use_expected_num_predict() -> None:
    summarizer = make_summarizer(RecordingClient(), num_ctx=8192)
    extract = summarizer._num_predict("extract")
    merge = summarizer._num_predict("merge")
    validate = summarizer._num_predict("validate")
    assert extract == int(8192 * EXTRACT_PREDICT_FRACTION)
    assert merge == int(8192 * FRONT_MATTER_PREDICT_FRACTION)
    assert validate == int(8192 * FRONT_MATTER_PREDICT_FRACTION)
    assert summarizer._num_predict("format") == int(8192 * DOCUMENT_PREDICT_FRACTION)
    assert merge < extract


def test_pack_groups_uses_context_budget_not_fixed_three() -> None:
    load_prompts()
    small = make_summarizer(RecordingClient(), num_ctx=2048)
    tiny_sections = [f"note {index}" for index in range(12)]
    small_groups = small._pack_groups(tiny_sections, "Merge these.")
    assert len(small_groups) >= 1
    assert sum(len(group) for group in small_groups) == 12

    large = make_summarizer(RecordingClient(), num_ctx=131072)
    large_groups = large._pack_groups(tiny_sections, "Merge these.")
    assert large_groups == [tiny_sections]


def test_pack_groups_splits_oversized_sections() -> None:
    load_prompts()
    summarizer = make_summarizer(RecordingClient(), num_ctx=2048)
    huge = "x" * (summarizer._prompt_char_budget())
    groups = summarizer._pack_groups([huge, huge, "tail"], "Merge")
    assert len(groups) >= 2
    assert [len(group) for group in groups][0] == 1


def test_summarize_stitches_every_extract_into_the_document() -> None:
    """The detailed body is the extracts themselves, never a second rewrite."""
    load_prompts()
    paragraph = "Speaker Alex discusses the grid engine. " * 250
    transcript = f"{paragraph}\n\n{paragraph} Jordan asks about GAS."
    client = RecordingClient(
        [
            "## Grid Engine\n- Alex explained UNIQUE_ALPHA in detail.",
            "## Ability System\n- Jordan raised UNIQUE_BETA as a blocker.",
            FRONT_MATTER,
            FRONT_MATTER,
        ]
    )
    summarizer = make_summarizer(client, num_ctx=8192)
    result = summarizer.summarize(transcript)

    assert "UNIQUE_ALPHA" in result
    assert "UNIQUE_BETA" in result
    assert result.startswith("# Weekly Sync")
    assert "## Grid Engine" in result
    assert "## Ability System" in result
    assert "Part 1 of 2" not in result

    chunk_prompts = [
        call["prompt"] for call in client.calls if get_prompt("chunk") in call["prompt"]
    ]
    assert len(chunk_prompts) == 2
    assert "Already recorded, background only" in chunk_prompts[1]
    assert "Topics already recorded: Grid Engine" in chunk_prompts[1]
    assert "[MORE SEGMENTS FOLLOW]" in chunk_prompts[0]
    assert "[END OF TRANSCRIPT]" in chunk_prompts[-1]
    assert all(call["options"]["num_ctx"] == 8192 for call in client.calls)

    merge_calls = [
        call for call in client.calls if get_prompt("merge") in call["prompt"]
    ]
    assert len(merge_calls) == 1
    assert all(
        call["options"]["num_predict"] == summarizer._num_predict("merge")
        for call in merge_calls
    )
    # Only the extract, overview, and validation passes ever see the notes: there is
    # no second generation of the detailed body.
    known_prompts = tuple(get_prompt(name) for name in ("chunk", "merge", "validate"))
    assert all(
        any(prompt in call["prompt"] for prompt in known_prompts)
        for call in client.calls
    )
    assert len(client.calls) == 4


def test_summarize_uses_the_selected_context_everywhere() -> None:
    """16k in means 16k on every Ollama call, at every stage."""
    load_prompts()
    paragraph = "Speaker Alex discusses the grid engine. " * 900
    transcript = f"{paragraph}\n\n{paragraph}"
    client = RecordingClient(["notes about GAS", "more notes", FRONT_MATTER, FRONT_MATTER])
    summarizer = make_summarizer(client, num_ctx=16384)
    summarizer.summarize(transcript)

    assert client.calls
    assert {call["options"]["num_ctx"] for call in client.calls} == {16384}
    allowed_limits = {
        summarizer._num_predict(stage) for stage in ("extract", "merge", "validate")
    }
    assert {call["options"]["num_predict"] for call in client.calls} <= allowed_limits


def test_summarize_parses_as_a_meeting_document() -> None:
    from speaker_transcriber.export.meeting_document import parse_meeting_markdown

    load_prompts()
    paragraph = "Speaker Alex discusses the grid engine. " * 250
    transcript = f"{paragraph}\n\n{paragraph} Jordan asks about GAS."
    extract = (
        "**Participants**\n- Alex\n\n**Action items**\n- Alex owns rollout\n\n"
        "**Risks / blockers**\n- UNIQUE_RISK pending"
    )
    client = RecordingClient([extract, extract, FRONT_MATTER, FRONT_MATTER])
    summarizer = make_summarizer(client, num_ctx=8192)
    summary = summarizer.summarize(transcript)
    document = parse_meeting_markdown(summary)

    assert document.title == "Weekly Sync"
    assert document.participants == "Alex, Jordan"
    assert document.has_action_table()
    assert not document.needs_format_pass()
    assert "UNIQUE_RISK" in summary
    # Both extracts are identical, so the body carries each item exactly once and
    # the per-segment participants block never reaches the document.
    assert summary.count("UNIQUE_RISK") == 1
    assert summary.count("Alex owns rollout") == 1
    titles = [section.title for section in document.sections]
    assert titles.count("Additional Risks and Blockers") == 1
    assert not any(title.startswith("Participants") for title in titles)


def test_validate_runs_once_and_never_shortens() -> None:
    load_prompts()
    extracts = [f"extract {index} details about GAS " * 3 for index in range(4)]
    client = RecordingClient(["Tiny."])
    summarizer = make_summarizer(client, num_ctx=8192)
    result = summarizer._validate(
        FRONT_MATTER,
        extracts,
        on_progress=None,
        on_chunk=None,
        on_section_break=None,
        on_reasoning=None,
        stage_start=0.8,
    )
    assert result == FRONT_MATTER
    assert len(client.calls) == 1
    assert get_prompt("validate") in client.calls[0]["prompt"]


def test_validate_is_skipped_when_extracts_do_not_fit() -> None:
    load_prompts()
    extracts = [f"extract {index} details about GAS " * 200 for index in range(10)]
    client = RecordingClient()
    summarizer = make_summarizer(client, num_ctx=1024)
    result = summarizer._validate(
        FRONT_MATTER,
        extracts,
        on_progress=None,
        on_chunk=None,
        on_section_break=None,
        on_reasoning=None,
        stage_start=0.8,
    )
    assert result == FRONT_MATTER
    assert client.calls == []


def test_truncated_output_is_continued() -> None:
    load_prompts()
    client = RecordingClient([" rest of the sentence."])
    summarizer = make_summarizer(client, num_ctx=8192)
    cap = int(summarizer._num_predict("extract") * 4 * 0.95)
    truncated = "x" * cap
    result = summarizer._ensure_complete(truncated, "extract")
    assert "rest of the sentence" in result
    assert len(client.calls) == 1
    assert get_prompt("continue") in client.calls[0]["prompt"]
    assert "Document so far" in client.calls[0]["prompt"]
    assert client.calls[0]["options"]["num_predict"] == summarizer._num_predict("extract")


def test_short_but_finished_output_is_not_continued() -> None:
    """Being shorter than the source is not truncation; regenerating costs hours."""
    load_prompts()
    client = RecordingClient(["should not be used"])
    summarizer = make_summarizer(client, num_ctx=8192)
    assert summarizer._ensure_complete(FRONT_MATTER, "merge") == FRONT_MATTER
    assert client.calls == []


def test_extract_without_document_sections_is_not_continued() -> None:
    load_prompts()
    client = RecordingClient(["should not be used"])
    summarizer = make_summarizer(client, num_ctx=8192)
    cap = int(summarizer._num_predict("extract") * 4 * 0.95)
    complete_extract = ("Alex owns the rollout. " * (cap // 22)).strip()
    assert summarizer._ensure_complete(complete_extract, "extract") == complete_extract
    assert client.calls == []


SAMPLE_EXTRACTS = [
    (
        "**Meeting Notes**\n\n"
        "**Participants**\n- Cash\n- GranSeba\n\n"
        "**Discussion**\n\n"
        "**Project Status and Technical Details**\n"
        "- Cash: the packaged build fails on the shader compile step.\n"
        "- GranSeba: the editor build still works, so it is packaging only.\n\n"
        "**Decisions**\n- No explicit decisions were recorded.\n\n"
        "**Questions**\n- None raised in this segment.\n\n"
        "[MORE SEGMENTS FOLLOW]"
    ),
    (
        "**Continuation Brief**\n\n"
        "**Participants**\n- Cash\n- GranSeba\n\n"
        "**Discussion**\n\n"
        "**Project Status and Technical Details (Recap)**\n"
        "- Cash: the packaged build fails on the shader compile step.\n"
        "- GranSeba: the editor build still works, so it is packaging only.\n"
        "- Cash: UNIQUE_DDC the derived data cache was stale and needed clearing.\n\n"
        "**Technical details**\n- Unreal Engine 5.4, MSVC 14.38.\n\n"
        "[MORE SEGMENTS FOLLOW]"
    ),
    (
        "**Recap of Previous Discussion**\n"
        "- The packaged build was failing on shader compilation.\n"
        "- The editor build kept working throughout.\n\n"
        "## Presentation Strategy\n"
        "- GranSeba: UNIQUE_DEMO record the demo before the Friday review.\n\n"
        "## Action items\n"
        "- Cash: clear the derived data cache before the next package.\n\n"
        "[END OF TRANSCRIPT]"
    ),
]


def test_assembled_body_has_no_per_segment_seams() -> None:
    """Nine near-identical scaffolds collapse into one section per topic."""
    summarizer = make_summarizer(RecordingClient(), num_ctx=8192)
    document = summarizer._assemble_document(FRONT_MATTER, SAMPLE_EXTRACTS)

    assert "Part 1 of" not in document
    assert "MORE SEGMENTS FOLLOW" not in document
    assert "END OF TRANSCRIPT" not in document
    assert "Meeting Notes" not in document
    assert "Continuation Brief" not in document
    assert "GranSeba" in document
    assert "## Participants" not in document
    assert "No explicit decisions were recorded" not in document
    assert "None raised in this segment" not in document

    assert document.count("## Project Status and Technical Details") == 1
    assert document.count("the packaged build fails on the shader compile step") == 1
    assert document.count("the editor build still works") == 1
    assert "The packaged build was failing on shader compilation" not in document

    for unique in ("UNIQUE_DDC", "UNIQUE_DEMO"):
        assert document.count(unique) == 1
    assert "Unreal Engine 5.4, MSVC 14.38" in document
    assert document.startswith("# Weekly Sync")


def test_assembled_body_parses_as_a_meeting_document() -> None:
    from speaker_transcriber.export.meeting_document import parse_meeting_markdown

    summarizer = make_summarizer(RecordingClient(), num_ctx=8192)
    document = parse_meeting_markdown(
        summarizer._assemble_document(FRONT_MATTER, SAMPLE_EXTRACTS)
    )
    titles = [section.title for section in document.sections]

    assert not document.needs_format_pass()
    assert titles.count("Project Status and Technical Details") == 1
    assert titles.count("Presentation Strategy") == 1
    assert titles.count("Technical Details") == 1
    assert len(titles) == len(set(titles))


def test_running_outline_carries_topics_not_label_blocks() -> None:
    """The next segment sees the topic list, never the Decisions block to copy."""
    summarizer = make_summarizer(RecordingClient(), num_ctx=8192)
    outline = summarizer._running_outline(SAMPLE_EXTRACTS[:2])

    assert "Topics already recorded: Project Status and Technical Details" in outline
    assert "Participants" not in outline
    assert len(outline) <= summarizer._running_char_budget()


def test_format_meeting_notes_uses_format_prompt() -> None:
    load_prompts()
    client = RecordingClient(["# Formatted\n\n**Participants:** Alex"])
    summarizer = make_summarizer(client, num_ctx=8192)
    result = summarizer.format_meeting_notes("loose notes about Alex")
    assert result.startswith("# Formatted")
    assert get_prompt("format") in client.calls[0]["prompt"]
    assert "loose notes about Alex" in client.calls[0]["prompt"]
    assert client.calls[0]["options"]["num_ctx"] == 8192
    assert client.calls[0]["options"]["num_predict"] == summarizer._num_predict("format")


def test_out_of_memory_errors_are_detected() -> None:
    assert is_out_of_memory_error("CUDA error: out of memory")
    assert is_out_of_memory_error(
        "model requires more system memory (9.0 GiB) than is available (5.1 GiB)"
    )
    assert is_out_of_memory_error("failed to allocate KV cache")
    assert is_out_of_memory_error(RuntimeError("cudaMalloc failed: out of memory"))
    assert not is_out_of_memory_error("model 'qwen3.5:9b' not found")
    assert not is_out_of_memory_error("connection refused")
    assert not is_out_of_memory_error("the zoom room booking failed")
    assert not is_out_of_memory_error("")
    assert not is_out_of_memory_error(None)


def test_generate_stream_raises_out_of_memory() -> None:
    load_prompts()
    client = FailingClient(RuntimeError("CUDA error: out of memory"))
    summarizer = make_summarizer(client, num_ctx=8192)
    with pytest.raises(OllamaOutOfMemoryError):
        summarizer._generate_stream("prompt", 100)


def test_summarize_propagates_out_of_memory() -> None:
    load_prompts()
    client = FailingClient(RuntimeError("model requires more system memory"))
    summarizer = make_summarizer(client, num_ctx=8192)
    with pytest.raises(OllamaOutOfMemoryError):
        summarizer.summarize("Alex talks about the grid engine.")


def test_summarize_wraps_other_failures() -> None:
    load_prompts()
    client = FailingClient(RuntimeError("model 'test-model' not found"))
    summarizer = make_summarizer(client, num_ctx=8192)
    with pytest.raises(RuntimeError, match="Could not summarize locally"):
        summarizer.summarize("Alex talks about the grid engine.")


def test_generate_stream_stops_when_already_cancelled() -> None:
    load_prompts()
    cancel = threading.Event()
    cancel.set()
    client = RecordingClient(["Hello"])
    summarizer = make_summarizer(client, num_ctx=8192)
    summarizer.cancel_event = cancel
    with pytest.raises(ProcessingCancelled):
        summarizer._generate_stream("prompt", 100)
    assert client.calls == []


def test_generate_stream_stops_mid_response() -> None:
    load_prompts()
    cancel = threading.Event()

    class CancellingClient:
        def generate(self, **kwargs):
            yield FakeChunk(response="Hello ")
            cancel.set()
            yield FakeChunk(response="world")

    summarizer = make_summarizer(CancellingClient(), num_ctx=8192)
    summarizer.cancel_event = cancel
    with pytest.raises(ProcessingCancelled):
        summarizer._generate_stream("prompt", 100)


def test_summarize_propagates_cancellation() -> None:
    load_prompts()
    cancel = threading.Event()
    cancel.set()
    summarizer = make_summarizer(RecordingClient(["ok"]), num_ctx=8192)
    summarizer.cancel_event = cancel
    with pytest.raises(ProcessingCancelled):
        summarizer.summarize("Alex talks about the grid engine.")


def test_the_style_picks_the_prompt_pack() -> None:
    load_prompts()
    client = RecordingClient(["Slide notes"])
    summarizer = make_summarizer(client, style="pitch_deck")
    summarizer._generate_stream(summarizer._chunk_prompt("Talk", "", True), 100)
    call = client.calls[0]
    assert call["system"] == get_prompt("system", "pitch_deck")
    assert get_prompt("chunk", "pitch_deck") in call["prompt"]
    assert get_prompt("chunk", "meeting_summary") not in call["prompt"]


def test_required_sections_are_style_specific() -> None:
    limit = 100
    near_cap = "word " * (limit * 4 // 5 - 1) + "end."
    meeting = make_summarizer(RecordingClient(), style="meeting_summary")
    transcript = make_summarizer(RecordingClient(), style="pure_transcription")
    assert meeting._looks_truncated(near_cap, limit, require_sections=True)
    assert not transcript._looks_truncated(near_cap, limit, require_sections=True)
    with_sections = near_cap + "\n\n## Action Items\n\n## Open Questions\n\n- None."
    assert not meeting._looks_truncated(with_sections, limit, require_sections=True)


def test_sequential_styles_concatenate_segments_without_merging() -> None:
    load_prompts()
    paragraph = "Alex talks about the grid engine in detail. " * 250
    transcript = f"{paragraph}\n\n{paragraph} Jordan asks about GAS."
    client = RecordingClient(
        [
            "**Alex:** UNIQUE_ALPHA is the grid engine.",
            "**Jordan:** UNIQUE_BETA is the ability system.",
        ]
    )
    summarizer = make_summarizer(client, style="pure_transcription")
    result = summarizer.summarize(transcript)
    assert result == (
        "**Alex:** UNIQUE_ALPHA is the grid engine.\n\n"
        "**Jordan:** UNIQUE_BETA is the ability system."
    )
    assert len(client.calls) == 2
    assert all(
        "Already recorded, background only" not in call["prompt"]
        for call in client.calls
    )


def test_document_styles_keep_only_the_merged_document() -> None:
    load_prompts()
    paragraph = "Alex talks about the offline pipeline in detail. " * 250
    transcript = f"{paragraph}\n\n{paragraph} Jordan asks about pricing."
    merged = "# Summit\n\n*A pitch.*\n\n## Problem\n\n- Studios cannot upload."
    client = RecordingClient(
        [
            "## Problem\n- UNIQUE_ALPHA blocks uploads.",
            "## Ask\n- UNIQUE_BETA engineers.",
            merged,
            merged,
        ]
    )
    summarizer = make_summarizer(client, style="pitch_deck")
    result = summarizer.summarize(transcript)
    assert result == merged
    assert "UNIQUE_ALPHA" not in result


def test_extract_context_length_from_modelinfo() -> None:
    class Info:
        modelinfo = {"qwen3.context_length": 32768}

    assert extract_context_length(Info()) == 32768
    assert extract_context_length({"parameters": "num_ctx 16384"}) == 16384
    assert extract_context_length({}) is None
