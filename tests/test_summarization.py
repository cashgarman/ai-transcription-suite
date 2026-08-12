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


def test_chunks_split_long_paragraph_on_sentences() -> None:
    summarizer = make_summarizer(RecordingClient())
    sentence = "This is a complete sentence about the meeting topic."
    paragraph = " ".join([sentence] * 120)
    assert len(paragraph) > summarizer.CHUNK_CHARACTER_LIMIT
    chunks = summarizer._chunks(paragraph)
    assert len(chunks) > 1
    assert all(len(chunk) <= summarizer.CHUNK_CHARACTER_LIMIT + len(sentence) for chunk in chunks)
    assert "".join(chunk.replace(" ", "") for chunk in chunks) == paragraph.replace(" ", "")


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
    paragraph = "Speaker Alex discusses the grid engine. " * 80
    transcript = f"{paragraph}\n\n{paragraph} Jordan asks about GAS."
    client = RecordingClient(
        [
            "Section one notes with Alex.",
            "Section two notes with Jordan.",
            "# Merged\n\nParticipants: Alex, Jordan",
            "# Validated\n\nParticipants: Alex, Jordan",
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


def test_validate_walks_chunks_when_transcript_is_large() -> None:
    load_prompts()
    summarizer = make_summarizer(
        RecordingClient(["corrected one", "corrected two"]),
        num_ctx=1024,
    )
    chunks = ["alpha " * 130, "beta " * 130]
    transcript = "\n\n".join(chunks)
    draft = "Draft " * 30
    result = summarizer._validate(
        transcript,
        draft,
        chunks,
        on_progress=None,
        on_chunk=None,
        on_section_break=None,
        on_reasoning=None,
        stage_start=0.8,
    )
    assert result == "corrected two"
    assert len(summarizer.client.calls) == 2
    assert "Transcript segment 1 of 2" in summarizer.client.calls[0]["prompt"]
    assert "Transcript segment 2 of 2" in summarizer.client.calls[1]["prompt"]
    assert get_prompt("validate") in summarizer.client.calls[0]["prompt"]


def test_format_meeting_notes_uses_format_prompt() -> None:
    load_prompts()
    client = RecordingClient(["# Formatted\n\n**Participants:** Alex"])
    summarizer = make_summarizer(client, num_ctx=8192)
    result = summarizer.format_meeting_notes("loose notes about Alex")
    assert result.startswith("# Formatted")
    assert get_prompt("format") in client.calls[0]["prompt"]
    assert "loose notes about Alex" in client.calls[0]["prompt"]
    assert client.calls[0]["options"]["num_ctx"] == 8192


def test_extract_context_length_from_modelinfo() -> None:
    class Info:
        modelinfo = {"qwen3.context_length": 32768}

    assert extract_context_length(Info()) == 32768
    assert extract_context_length({"parameters": "num_ctx 16384"}) == 16384
    assert extract_context_length({}) is None
