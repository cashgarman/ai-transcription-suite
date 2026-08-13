from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from speaker_transcriber.errors import ProcessingCancelled
from speaker_transcriber.models.model_manager import ModelManager
from speaker_transcriber.pipeline.types import RawSegment


LOGGER = logging.getLogger("speaker_transcriber.alignment")


class Aligner:
    def __init__(self, model_manager: ModelManager) -> None:
        self.model_manager = model_manager

    def align(
        self,
        audio_path: Path,
        segments: list[RawSegment],
        language: str,
        device: str,
        cancel_event: threading.Event,
        on_progress: Callable[[float], None] | None = None,
        model_name: str | None = None,
    ) -> list[RawSegment]:
        import whisperx

        if cancel_event.is_set():
            raise ProcessingCancelled()
        align_model = (model_name or "").strip()
        if align_model.lower() in {"", "auto"}:
            align_model = None
        LOGGER.info(
            "Loading WhisperX alignment model for language=%s on %s (%s)",
            language,
            device,
            align_model or "language default",
        )
        model = None
        try:
            load_kwargs: dict[str, object] = {
                "language_code": language,
                "device": device,
            }
            if align_model:
                load_kwargs["model_name"] = align_model
            model, metadata = whisperx.load_align_model(**load_kwargs)
            if on_progress:
                on_progress(0.2)
            audio = whisperx.load_audio(str(audio_path))
            source_segments = [
                {"start": segment.start, "end": segment.end, "text": segment.text}
                for segment in segments
            ]
            result = whisperx.align(
                source_segments,
                model,
                metadata,
                audio,
                device,
                return_char_alignments=False,
            )
            if cancel_event.is_set():
                raise ProcessingCancelled()
            aligned: list[RawSegment] = []
            for item in result.get("segments", []):
                words = []
                for word in item.get("words", []):
                    if "start" not in word or "end" not in word:
                        continue
                    words.append(
                        {
                            "word": str(word.get("word", "")).strip(),
                            "start": float(word["start"]),
                            "end": float(word["end"]),
                            "score": float(word.get("score", 0.0)),
                        }
                    )
                aligned.append(
                    RawSegment(
                        start=float(item.get("start", 0.0)),
                        end=float(item.get("end", 0.0)),
                        text=str(item.get("text", "")).strip(),
                        words=words,
                    )
                )
            if on_progress:
                on_progress(1.0)
            LOGGER.info("Alignment complete: %d segments", len(aligned))
            return aligned
        finally:
            if model is not None:
                del model
            self.model_manager.clear_cuda()
