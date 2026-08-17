import io
import subprocess
import threading
from types import SimpleNamespace

from speaker_transcriber.audio import ffmpeg


def test_is_supported_media_accepts_audio_only_formats() -> None:
    assert ffmpeg.is_supported_media("recording.mp3")
    assert ffmpeg.is_supported_media("recording.MP3")
    assert ffmpeg.is_supported_media("/media/podcast.wav")
    assert not ffmpeg.is_supported_media("notes.txt")


def test_media_file_dialog_filter_includes_mp3_and_uses_semicolons() -> None:
    dialog_filter = ffmpeg.media_file_dialog_filter()
    assert "*.mp3" in dialog_filter
    assert "Audio files" in dialog_filter
    assert "*.mp4" in dialog_filter
    assert "Video files" in dialog_filter
    assert ";;" in dialog_filter


def test_probe_media_reads_duration_and_audio_stream(tmp_path, monkeypatch) -> None:
    source = tmp_path / "meeting.mp4"
    source.write_bytes(b"media")
    monkeypatch.setattr(ffmpeg, "_require_executable", lambda name: name)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout='{"format":{"duration":"12.5"},"streams":[{"codec_type":"audio"}]}',
            stderr="",
        ),
    )
    result = ffmpeg.probe_media(source)
    assert result.duration_seconds == 12.5
    assert result.has_audio


def test_probe_media_accepts_mp3_extension(tmp_path, monkeypatch) -> None:
    source = tmp_path / "recording.mp3"
    source.write_bytes(b"audio")
    monkeypatch.setattr(ffmpeg, "_require_executable", lambda name: name)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout='{"format":{"duration":"42.0"},"streams":[{"codec_type":"audio"}]}',
            stderr="",
        ),
    )
    result = ffmpeg.probe_media(source)
    assert result.duration_seconds == 42.0
    assert result.has_audio


def test_extract_audio_reports_ffmpeg_progress(tmp_path, monkeypatch) -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = io.StringIO("out_time_ms=5000000\nprogress=end\n")
            self.stderr = io.StringIO("")
            self.returncode = None

        def poll(self):
            if self.stdout.tell() == len(self.stdout.getvalue()):
                return 0
            return None

        def wait(self, timeout=None):
            self.returncode = 0
            return 0

        def terminate(self):
            self.returncode = 0

        def kill(self):
            self.returncode = 1

    monkeypatch.setattr(ffmpeg, "_require_executable", lambda name: name)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    progress = []
    ffmpeg.extract_audio(
        tmp_path / "input.mp4",
        tmp_path / "audio.wav",
        10.0,
        threading.Event(),
        progress.append,
    )
    assert progress == [0.5, 1.0]


def test_extract_audio_passes_duration_limit_to_ffmpeg(tmp_path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = io.StringIO("progress=end\n")
            self.stderr = io.StringIO("")
            self.returncode = None

        def poll(self):
            if self.stdout.tell() == len(self.stdout.getvalue()):
                return 0
            return None

        def wait(self, timeout=None):
            self.returncode = 0
            return 0

        def terminate(self):
            self.returncode = 0

        def kill(self):
            self.returncode = 1

    def fake_popen(command, **kwargs):
        captured["command"] = list(command)
        return FakeProcess()

    monkeypatch.setattr(ffmpeg, "_require_executable", lambda name: name)
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    ffmpeg.extract_audio(
        tmp_path / "input.mp4",
        tmp_path / "audio.wav",
        600.0,
        threading.Event(),
        None,
        max_duration_seconds=600.0,
    )
    command = captured["command"]
    assert "-t" in command
    assert command[command.index("-t") + 1] == "600.0"


def test_encode_wav_to_mp3_invokes_lame(tmp_path, monkeypatch) -> None:
    source = tmp_path / "speech.wav"
    source.write_bytes(b"RIFF")
    destination = tmp_path / "speech.mp3"
    captured: dict[str, object] = {}
    monkeypatch.setattr(ffmpeg, "_require_executable", lambda name: name)

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ffmpeg.encode_wav_to_mp3(source, destination, threading.Event())
    command = captured["command"]
    assert "-codec:a" in command
    assert "libmp3lame" in command
    assert str(destination) in command


def test_stretch_wav_tempo_uses_atempo_chain(tmp_path, monkeypatch) -> None:
    source = tmp_path / "speech.wav"
    source.write_bytes(b"RIFF")
    destination = tmp_path / "speech.t400.wav"
    captured: dict[str, object] = {}
    monkeypatch.setattr(ffmpeg, "_require_executable", lambda name: name)

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ffmpeg.stretch_wav_tempo(source, destination, 4.0, threading.Event())
    command = captured["command"]
    assert "-filter:a" in command
    graph = command[command.index("-filter:a") + 1]
    assert graph == "atempo=2,atempo=2"
