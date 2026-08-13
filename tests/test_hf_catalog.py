import sys
from types import ModuleType, SimpleNamespace

import pytest

from speaker_transcriber.models.hf_catalog import (
    AlignmentCatalogProvider,
    DiarizationCatalogProvider,
    WhisperCatalogProvider,
    _catalog_size,
    _is_gated,
    _is_pyannote_pipeline_candidate,
    _repo_size,
    _sibling_size,
)
from speaker_transcriber.models.model_catalog import (
    DEFAULT_DIARIZATION_MODEL,
    RECOMMENDED_ALIGNMENT_MODEL,
    huggingface_cache_dir,
    whisper_runtime_id,
)


@pytest.fixture
def fake_hub(monkeypatch) -> ModuleType:
    """A stand-in huggingface_hub module.

    The code under test imports huggingface_hub lazily inside each function,
    so planting a fake in sys.modules lets these tests exercise the real
    retry and rejection logic without the heavy dependency being installed.
    Tests assign only the functions they expect the code to call; anything
    else fails with an ImportError, which is the point.
    """
    module = ModuleType("huggingface_hub")
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)
    return module


class FakeSibling:
    def __init__(self, size: int) -> None:
        self.size = size


class FakeModel:
    def __init__(self, repo_id: str, size: int = 0, gated: object = False) -> None:
        self.id = repo_id
        self.siblings = [FakeSibling(size)] if size else []
        self.gated = gated
        self.pipeline_tag = "automatic-speech-recognition"


def test_sibling_size_sums_files() -> None:
    info = FakeModel("repo", size=0)
    info.siblings = [FakeSibling(100), FakeSibling(50), {"size": 25}]
    assert _sibling_size(info) == 175


def test_repo_size_prefers_used_storage() -> None:
    info = FakeModel("repo")
    info.used_storage = 9_000_000
    assert _repo_size(info) == 9_000_000
    assert _catalog_size(info, token=None) == 9_000_000


def test_is_gated_treats_auto_as_gated() -> None:
    assert _is_gated(SimpleNamespace(gated="auto"))
    assert not _is_gated(SimpleNamespace(gated=False))
    assert not _is_gated(SimpleNamespace(gated=None))


def test_whisper_catalog_pins_large_v3(monkeypatch) -> None:
    listed = [
        FakeModel("Systran/faster-whisper-large-v3", 3_000_000_000),
        FakeModel("Systran/faster-whisper-tiny", 75_000_000),
    ]

    class FakeApi:
        def list_models(self, **kwargs):
            return listed

        def model_info(self, repo_id, files_metadata=False):
            return FakeModel(repo_id, 1_000_000)

    monkeypatch.setattr(
        "speaker_transcriber.models.hf_catalog._hf_api",
        lambda token=None: FakeApi(),
    )
    monkeypatch.setattr(
        "speaker_transcriber.models.hf_catalog.hf_repo_cached",
        lambda repo_id: repo_id.endswith("large-v3"),
    )
    entries = WhisperCatalogProvider().list_models()
    assert entries[0].name == "large-v3"
    assert whisper_runtime_id("openai/whisper-large-v3") == entries[0].name
    assert entries[0].installed
    names = [entry.name for entry in entries]
    assert "tiny" in names
    assert "distil-large-v3" in names
    assert "medium" in names


def test_alignment_catalog_pins_english_wav2vec(monkeypatch) -> None:
    class FakeApi:
        def list_models(self, **kwargs):
            return [
                FakeModel("jonatasgrosman/wav2vec2-large-xlsr-53-english", 1_200_000_000),
                FakeModel("facebook/wav2vec2-large-960h", 800_000_000),
                FakeModel("openai/whisper-large-v3", 3_000_000_000),
            ]

        def model_info(self, repo_id, files_metadata=False):
            return FakeModel(repo_id, 1_200_000_000)

    monkeypatch.setattr(
        "speaker_transcriber.models.hf_catalog._hf_api",
        lambda token=None: FakeApi(),
    )
    monkeypatch.setattr(
        "speaker_transcriber.models.hf_catalog.hf_repo_cached",
        lambda repo_id: False,
    )
    entries = AlignmentCatalogProvider().list_models()
    assert entries[0].name == RECOMMENDED_ALIGNMENT_MODEL
    assert entries[0].role == "English wav2vec2"
    names = [entry.name for entry in entries]
    assert "facebook/wav2vec2-large-960h" in names
    assert all("whisper" not in name.lower() for name in names)


def test_diarization_catalog_marks_pyannote_gated(monkeypatch) -> None:
    class FakeApi:
        def list_models(self, **kwargs):
            return [
                FakeModel("pyannote/speaker-diarization-3.1", gated=True),
                FakeModel("other/speaker-diarization-demo", gated=False),
            ]

        def model_info(self, repo_id, files_metadata=False):
            return FakeModel(repo_id, gated=True)

    monkeypatch.setattr(
        "speaker_transcriber.models.hf_catalog._hf_api",
        lambda token=None: FakeApi(),
    )
    monkeypatch.setattr(
        "speaker_transcriber.models.hf_catalog.hf_repo_cached",
        lambda repo_id: False,
    )
    entries = DiarizationCatalogProvider().list_models()
    assert entries[0].name == DEFAULT_DIARIZATION_MODEL
    assert entries[0].gated
    assert entries[1].name == "pyannote/speaker-diarization-3.0"
    assert entries[1].gated
    demo = next(entry for entry in entries if entry.name.endswith("demo"))
    assert not demo.gated


def test_diarization_fills_size_from_model_info(monkeypatch) -> None:
    listed = FakeModel("other/speaker-diarization-demo")

    class FakeApi:
        def list_models(self, **kwargs):
            return [listed]

        def model_info(self, repo_id, files_metadata=False):
            info = FakeModel(repo_id)
            info.used_storage = 250_000_000 if repo_id.endswith("demo") else 1_000_000
            return info

    monkeypatch.setattr(
        "speaker_transcriber.models.hf_catalog._hf_api",
        lambda token=None: FakeApi(),
    )
    monkeypatch.setattr(
        "speaker_transcriber.models.hf_catalog.hf_repo_cached",
        lambda repo_id: False,
    )
    entries = DiarizationCatalogProvider().list_models()
    demo = next(entry for entry in entries if entry.name.endswith("demo"))
    assert demo.size_bytes == 250_000_000


def test_huggingface_cache_dir_uses_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)
    assert huggingface_cache_dir() == tmp_path / "hub"


def test_hf_repo_cached_detects_blobs_without_snapshots(monkeypatch, tmp_path) -> None:
    from speaker_transcriber.models.model_catalog import hf_repo_cached

    hub = tmp_path / "hub"
    monkeypatch.setenv("HF_HUB_CACHE", str(hub))
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)
    folder = hub / "models--org--demo"
    (folder / "blobs").mkdir(parents=True)
    (folder / "blobs" / "abc").write_bytes(b"weights")
    assert hf_repo_cached("org/demo")
    assert not hf_repo_cached("org/missing")


def test_retry_hub_operation_retries_connection_reset(monkeypatch) -> None:
    from speaker_transcriber.huggingface_setup import retry_hub_operation

    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise OSError("[WinError 10054] An existing connection was forcibly closed by the remote host")
        return "ok"

    monkeypatch.setattr("speaker_transcriber.huggingface_setup.time.sleep", lambda _seconds: None)
    assert retry_hub_operation(flaky, max_attempts=5, what="test") == "ok"
    assert attempts["count"] == 3


def test_snapshot_download_explains_connection_reset(monkeypatch, fake_hub) -> None:
    from threading import Event

    from speaker_transcriber.models.hf_catalog import _snapshot_download

    monkeypatch.setattr(
        "speaker_transcriber.huggingface_setup.configure_huggingface_client",
        lambda: None,
    )
    monkeypatch.setattr("speaker_transcriber.huggingface_setup.time.sleep", lambda _seconds: None)

    def boom(**kwargs):
        raise OSError("[WinError 10054] An existing connection was forcibly closed by the remote host")

    fake_hub.snapshot_download = boom
    try:
        _snapshot_download("Systran/faster-whisper-tiny", None, None, Event())
    except RuntimeError as exc:
        assert "HF_HUB_INSECURE_SSL=1" in str(exc)
        assert "Systran/faster-whisper-tiny" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")


def test_404_entry_not_found_is_not_retryable() -> None:
    from speaker_transcriber.huggingface_setup import is_retryable_download_error

    class RemoteEntryNotFoundError(OSError):
        status_code = 404

        def __str__(self) -> str:
            return (
                "404 Client Error. Entry Not Found for url: "
                "https://huggingface.co/FluidInference/speaker-diarization-coreml/"
                "resolve/main/config.yaml."
            )

    assert not is_retryable_download_error(RemoteEntryNotFoundError())
    assert not is_retryable_download_error(
        OSError(
            "404 Client Error. Entry Not Found for url: "
            "https://huggingface.co/org/model/resolve/main/config.yaml."
        )
    )


def test_prefetch_rejects_coreml_without_config_yaml(monkeypatch, fake_hub) -> None:
    from speaker_transcriber.huggingface_setup import prefetch_diarization_models

    monkeypatch.setattr(
        "speaker_transcriber.huggingface_setup.configure_huggingface_client",
        lambda: None,
    )
    monkeypatch.setattr(
        "speaker_transcriber.huggingface_setup.patch_hf_hub_use_auth_token",
        lambda: None,
    )
    calls: list[str] = []

    def fake_list_repo_files(repo_id, token=None):
        return ["config.json", "README.md", "Segmentation.mlmodelc/model.mil"]

    def fake_snapshot(*args, **kwargs):
        calls.append("snapshot")

    def fake_hub_download(*args, **kwargs):
        calls.append("file")
        raise AssertionError("should not download config.yaml")

    fake_hub.list_repo_files = fake_list_repo_files
    fake_hub.snapshot_download = fake_snapshot
    fake_hub.hf_hub_download = fake_hub_download
    try:
        prefetch_diarization_models("token", "FluidInference/speaker-diarization-coreml")
    except RuntimeError as exc:
        message = str(exc)
        assert "FluidInference/speaker-diarization-coreml" in message
        assert "config.yaml" in message
        assert "CoreML" in message
    else:
        raise AssertionError("Expected RuntimeError")
    assert calls == []


def test_prefetch_custom_pipeline_uses_snapshot_only(monkeypatch, fake_hub) -> None:
    from speaker_transcriber.huggingface_setup import prefetch_diarization_models

    monkeypatch.setattr(
        "speaker_transcriber.huggingface_setup.configure_huggingface_client",
        lambda: None,
    )
    monkeypatch.setattr(
        "speaker_transcriber.huggingface_setup.patch_hf_hub_use_auth_token",
        lambda: None,
    )
    calls: list[tuple] = []

    def fake_list_repo_files(repo_id, token=None):
        return ["config.yaml", "README.md"]

    def fake_snapshot(repo_id, token=None):
        calls.append(("snapshot", repo_id))

    def fake_hub_download(repo_id, filename, token=None):
        calls.append(("file", repo_id, filename))

    fake_hub.list_repo_files = fake_list_repo_files
    fake_hub.snapshot_download = fake_snapshot
    fake_hub.hf_hub_download = fake_hub_download
    prefetch_diarization_models("token", "acme/speaker-diarization-custom")
    assert calls == [("snapshot", "acme/speaker-diarization-custom")]


def test_diarization_catalog_skips_coreml_and_onnx(monkeypatch) -> None:
    class FakeApi:
        def list_models(self, **kwargs):
            return [
                FakeModel("FluidInference/speaker-diarization-coreml"),
                FakeModel("acme/speaker-diarization-onnx"),
                FakeModel("other/speaker-diarization-demo"),
            ]

        def model_info(self, repo_id, files_metadata=False):
            return FakeModel(repo_id)

    monkeypatch.setattr(
        "speaker_transcriber.models.hf_catalog._hf_api",
        lambda token=None: FakeApi(),
    )
    monkeypatch.setattr(
        "speaker_transcriber.models.hf_catalog.hf_repo_cached",
        lambda repo_id: False,
    )
    names = [entry.name for entry in DiarizationCatalogProvider().list_models()]
    assert "FluidInference/speaker-diarization-coreml" not in names
    assert "acme/speaker-diarization-onnx" not in names
    assert "other/speaker-diarization-demo" in names


def test_pyannote_pipeline_candidate_requires_config_yaml_when_listed() -> None:
    info = FakeModel("org/speaker-diarization-weights")
    info.siblings = [SimpleNamespace(rfilename="config.json"), SimpleNamespace(rfilename="model.bin")]
    assert not _is_pyannote_pipeline_candidate("org/speaker-diarization-weights", info)
    info.siblings.append(SimpleNamespace(rfilename="config.yaml"))
    assert _is_pyannote_pipeline_candidate("org/speaker-diarization-weights", info)
    assert not _is_pyannote_pipeline_candidate("FluidInference/speaker-diarization-coreml")
