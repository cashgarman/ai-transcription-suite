from speaker_transcriber.models.summarization import (
    OllamaModelInfo,
    RequirementsSummarizer,
    extract_generate_chunk_parts,
    format_approx_vram,
)


class FakeChunk:
    def __init__(self, response: str = "", thinking: str = "") -> None:
        self.response = response
        self.thinking = thinking


def test_extract_generate_chunk_parts_reads_response_and_thinking() -> None:
    assert extract_generate_chunk_parts(FakeChunk("Hello", "Reasoning")) == (
        "Hello",
        "Reasoning",
    )
    assert extract_generate_chunk_parts({"response": "Hi", "thinking": "Think"}) == (
        "Hi",
        "Think",
    )


def test_generate_stream_falls_back_to_thinking(monkeypatch) -> None:
    class FakeClient:
        def generate(self, **kwargs):
            yield FakeChunk(response="", thinking="Draft summary")
            yield FakeChunk(response=" Final", thinking="")

    summarizer = RequirementsSummarizer()
    summarizer.client = FakeClient()
    chunks: list[str] = []
    result = summarizer._generate_stream("prompt", 100, chunks.append)
    assert result == "Final"
    assert "".join(chunks) == "Draft summary Final"
    assert summarizer.num_ctx == 8192


def test_format_approx_vram_gigabytes() -> None:
    assert format_approx_vram(5_500_000_000) == "~5.1 GB"


def test_format_approx_vram_megabytes() -> None:
    assert format_approx_vram(80_000_000) == "~76 MB"


def test_format_approx_vram_unknown() -> None:
    assert format_approx_vram(None) == "—"
    assert format_approx_vram(0) == "—"


def test_list_available_models_parses_size(monkeypatch) -> None:
    class FakeModel:
        def __init__(self, model: str, size: int) -> None:
            self.model = model
            self.size = size

    class FakeResponse:
        models = [
            FakeModel("qwen3.5:9b", 6_000_000_000),
            FakeModel("gemma3:1b", 900_000_000),
        ]

    class FakeClient:
        def list(self):
            return FakeResponse()

    monkeypatch.setattr(
        "ollama.Client",
        lambda: FakeClient(),
    )
    models = RequirementsSummarizer.list_available_models()
    assert len(models) == 2
    assert models[0] == OllamaModelInfo("gemma3:1b", 900_000_000)
    assert models[1].approx_vram_label == "~5.6 GB"
