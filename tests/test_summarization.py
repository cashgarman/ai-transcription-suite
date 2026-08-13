from speaker_transcriber.models.summarization import (
    RequirementsSummarizer,
    extract_context_length,
)
from speaker_transcriber.prompts import get_prompt, load_prompts


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


def make_summarizer(
    client: RecordingClient,
    num_ctx: int = 8192,
) -> RequirementsSummarizer:
    summarizer = RequirementsSummarizer.__new__(RequirementsSummarizer)
    summarizer.model_name = "test-model"
    summarizer.num_ctx = num_ctx
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


def test_document_stages_use_higher_num_predict() -> None:
    summarizer = make_summarizer(RecordingClient(), num_ctx=8192)
    extract = summarizer._num_predict("extract")
    merge = summarizer._num_predict("merge")
    validate = summarizer._num_predict("validate")
    assert extract == max(512, int(8192 * 0.35))
    assert merge == max(512, int(8192 * 0.50))
    assert validate == max(512, int(8192 * 0.70))
    assert extract < merge < validate


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


def test_summarize_includes_prior_context_and_validates() -> None:
    load_prompts()
    paragraph = "Speaker Alex discusses the grid engine. " * 250
    transcript = f"{paragraph}\n\n{paragraph} Jordan asks about GAS."
    client = RecordingClient(
        [
            "Section one notes with Alex.",
            "Section two notes with Jordan.",
            "# Merged\n\nParticipants: Alex, Jordan\n\n## Action Items\n\nNone.",
            "# Validated\n\nParticipants: Alex, Jordan\n\n## Action Items\n\nNone.",
        ]
    )
    summarizer = make_summarizer(client, num_ctx=8192)
    result = summarizer.summarize(transcript)
    assert "Validated" in result
    assert len(client.calls) >= 4
    chunk_prompts = [
        call["prompt"]
        for call in client.calls
        if get_prompt("chunk") in call["prompt"]
    ]
    assert len(chunk_prompts) >= 2
    assert "Context from earlier in this meeting" in chunk_prompts[1]
    assert "[MORE SEGMENTS FOLLOW]" in chunk_prompts[0]
    assert "[END OF TRANSCRIPT]" in chunk_prompts[-1]
    validate_prompts = [
        call["prompt"]
        for call in client.calls
        if get_prompt("validate") in call["prompt"]
    ]
    assert validate_prompts
    assert "Draft summary" in validate_prompts[0] or "Current draft" in validate_prompts[0]
    assert all(call["options"]["num_ctx"] == 8192 for call in client.calls)
    extract_predict = summarizer._num_predict("extract")
    merge_predict = summarizer._num_predict("merge")
    validate_predict = summarizer._num_predict("validate")
    chunk_calls = [
        call for call in client.calls if get_prompt("chunk") in call["prompt"]
    ]
    merge_calls = [
        call for call in client.calls if get_prompt("merge") in call["prompt"]
    ]
    assert all(call["options"]["num_predict"] == extract_predict for call in chunk_calls)
    assert merge_calls
    assert all(call["options"]["num_predict"] == merge_predict for call in merge_calls)
    assert all(
        call["options"]["num_predict"] == validate_predict
        for call in client.calls
        if get_prompt("validate") in call["prompt"]
    )


def test_validate_does_not_rewrite_once_per_extract() -> None:
    load_prompts()
    extracts = [f"extract {index} details about GAS " * 80 for index in range(10)]
    draft = "Draft meeting notes. " * 40
    client = RecordingClient(["NONE"] * 8)
    summarizer = make_summarizer(client, num_ctx=1024)
    result = summarizer._validate(
        draft,
        extracts,
        on_progress=None,
        on_chunk=None,
        on_section_break=None,
        on_reasoning=None,
        stage_start=0.8,
    )
    assert result == draft
    assert 1 <= len(client.calls) <= 4
    assert len(client.calls) < len(extracts)
    assert all("Transcript segment" not in call["prompt"] for call in client.calls)


def test_truncated_document_is_continued() -> None:
    load_prompts()
    client = RecordingClient(
        [
            " rest of the sentence.\n\n## Action Items\n\nNone.\n\n## Open Questions\n\nNone."
        ]
    )
    summarizer = make_summarizer(client, num_ctx=8192)
    cap = int(summarizer._num_predict("validate") * 4 * 0.95)
    truncated = "x" * cap
    result = summarizer._ensure_complete(truncated, "validate")
    assert "rest of the sentence" in result
    assert "Action Items" in result
    assert len(client.calls) == 1
    assert get_prompt("continue") in client.calls[0]["prompt"]
    assert "Document so far" in client.calls[0]["prompt"]
    assert client.calls[0]["options"]["num_predict"] == summarizer._num_predict(
        "validate"
    )


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


def test_extract_context_length_from_modelinfo() -> None:
    class Info:
        modelinfo = {"qwen3.context_length": 32768}

    assert extract_context_length(Info()) == 32768
    assert extract_context_length({"parameters": "num_ctx 16384"}) == 16384
    assert extract_context_length({}) is None
