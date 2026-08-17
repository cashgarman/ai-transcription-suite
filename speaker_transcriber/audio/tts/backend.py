from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path
from typing import Protocol

from speaker_transcriber.audio.tts.types import SystemVoice, VoiceGender
from speaker_transcriber.errors import TtsError

_HOST_SCRIPT = r"""
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  while ($true) {
    $line = [Console]::In.ReadLine()
    if ($null -eq $line) { break }
    if ($line -eq 'quit') { break }
    $job = $line | ConvertFrom-Json
    if ($job.action -eq 'list') {
      $voices = New-Object System.Collections.Generic.List[object]
      foreach ($installed in $synth.GetInstalledVoices()) {
        $info = $installed.VoiceInfo
        $voices.Add(@{
          id = [string]$info.Name
          name = [string]$info.Name
          gender = [string]$info.Gender
        })
      }
      $payload = @{ voices = $voices }
      Write-Output ($payload | ConvertTo-Json -Compress -Depth 5)
    }
    elseif ($job.action -eq 'speak') {
      try {
        $synth.SelectVoice([string]$job.voice)
        $synth.SetOutputToWaveFile([string]$job.output)
        $text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String([string]$job.text_b64))
        $synth.Speak($text)
        $synth.SetOutputToNull()
        Write-Output 'ok'
      } catch {
        try { $synth.SetOutputToNull() } catch {}
        Write-Output ('err:' + $_.Exception.Message)
      }
    }
    else {
      Write-Output 'err:unknown action'
    }
  }
} finally {
  $synth.Dispose()
}
"""


class TtsBackend(Protocol):
    def list_voices(self) -> list[SystemVoice]: ...

    def synthesize(self, text: str, voice_id: str, output_wav: Path) -> None: ...

    def close(self) -> None: ...


def _parse_gender(raw: str) -> VoiceGender:
    lowered = (raw or "").strip().lower()
    if lowered == "male":
        return "male"
    if lowered == "female":
        return "female"
    return "neutral"


class WindowsTtsBackend:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise TtsError("Text-to-speech is only available on Windows.")
        self._process: subprocess.Popen[str] | None = None

    def list_voices(self) -> list[SystemVoice]:
        payload = self._request({"action": "list"})
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise TtsError("Windows speech could not list installed voices.") from exc
        voices_raw = parsed.get("voices", parsed if isinstance(parsed, list) else [])
        if isinstance(voices_raw, dict):
            voices_raw = [voices_raw]
        voices: list[SystemVoice] = []
        for item in voices_raw or []:
            voice_id = str(item.get("id") or item.get("name") or "").strip()
            if not voice_id:
                continue
            voices.append(
                SystemVoice(
                    id=voice_id,
                    name=str(item.get("name") or voice_id),
                    gender=_parse_gender(str(item.get("gender") or "")),
                )
            )
        return voices

    def synthesize(self, text: str, voice_id: str, output_wav: Path) -> None:
        output_wav.parent.mkdir(parents=True, exist_ok=True)
        encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
        reply = self._request(
            {
                "action": "speak",
                "voice": voice_id,
                "output": str(output_wav.resolve()),
                "text_b64": encoded,
            }
        )
        if reply != "ok":
            detail = reply.removeprefix("err:").strip() if reply.startswith("err:") else reply
            raise TtsError(
                f"Windows speech could not render the segment with voice '{voice_id}'. {detail}".strip()
            )
        if not output_wav.is_file() or output_wav.stat().st_size == 0:
            raise TtsError("Windows speech did not write an audio file.")

    def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.write("quit\n")
                process.stdin.flush()
        except OSError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)

    def _ensure_process(self) -> subprocess.Popen[str]:
        if self._process is not None and self._process.poll() is None:
            return self._process
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._process = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-STA",
                "-NonInteractive",
                "-Command",
                _HOST_SCRIPT,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
        return self._process

    def _request(self, payload: dict) -> str:
        process = self._ensure_process()
        if process.stdin is None or process.stdout is None:
            raise TtsError("Windows speech host is not available.")
        try:
            process.stdin.write(json.dumps(payload, ensure_ascii=True) + "\n")
            process.stdin.flush()
            reply = process.stdout.readline()
        except OSError as exc:
            raise TtsError("Windows speech host stopped unexpectedly.") from exc
        if not reply:
            stderr = ""
            if process.stderr is not None:
                try:
                    stderr = process.stderr.read()
                except OSError:
                    stderr = ""
            raise TtsError(
                "Windows speech host stopped unexpectedly."
                + (f" {stderr.strip()[-1000:]}" if stderr.strip() else "")
            )
        return reply.strip()
