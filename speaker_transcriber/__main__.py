from __future__ import annotations

import argparse
import logging
import sys
import threading
from pathlib import Path

from speaker_transcriber.config import SettingsStore
from speaker_transcriber.cuda_setup import configure_cuda_libraries
from speaker_transcriber.huggingface_compat import patch_hf_hub_use_auth_token
from speaker_transcriber.huggingface_setup import configure_huggingface_client
from speaker_transcriber.pytorch_compat import patch_torch_load_weights_only
from speaker_transcriber.speechbrain_compat import patch_speechbrain_lazy_modules
from speaker_transcriber.errors import ProcessingCancelled, SpeakerTranscriberError
from speaker_transcriber.export import EXPORTERS, export_result
from speaker_transcriber.logging_config import configure_logging, log_system_information
from speaker_transcriber.pipeline.processor import TranscriptionProcessor
from speaker_transcriber.pipeline.types import ProcessingOptions, ProgressUpdate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="speaker-transcriber",
        description="Transcribe local media with word timestamps and speaker labels.",
    )
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--model",
        choices=("medium", "distil-large-v3", "large-v3"),
        default="distil-large-v3",
    )
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--compute-type", default="int8_float16")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--language", default="auto")
    parser.add_argument("--num-speakers", type=int)
    parser.add_argument("--min-speakers", type=int)
    parser.add_argument("--max-speakers", type=int)
    parser.add_argument("--alignment-device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--diarization-device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument(
        "--formats",
        default="txt,json",
        help=f"Comma-separated formats: {','.join(EXPORTERS)}",
    )
    parser.add_argument(
        "--hf-token",
        help="Hugging Face token (prefer HF_TOKEN to avoid process-list exposure)",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    formats = [item.strip().lower() for item in arguments.formats.split(",") if item.strip()]
    unsupported = sorted(set(formats) - set(EXPORTERS))
    if unsupported:
        parser.error(f"unsupported formats: {', '.join(unsupported)}")

    configure_cuda_libraries()
    configure_huggingface_client()
    patch_hf_hub_use_auth_token()
    patch_torch_load_weights_only()
    patch_speechbrain_lazy_modules()
    logger = configure_logging(arguments.verbose)
    log_system_information(logger)
    settings_store = SettingsStore()
    options = ProcessingOptions(
        model=arguments.model,
        device=arguments.device,
        compute_type=arguments.compute_type,
        batch_size=arguments.batch_size,
        language=arguments.language,
        num_speakers=arguments.num_speakers,
        min_speakers=arguments.min_speakers,
        max_speakers=arguments.max_speakers,
        alignment_device=arguments.alignment_device,
        diarization_device=arguments.diarization_device,
        hf_token=settings_store.get_hf_token(arguments.hf_token),
    )
    cancel_event = threading.Event()
    last_percent = -1

    def progress(update: ProgressUpdate) -> None:
        nonlocal last_percent
        percent = int(update.progress * 100)
        if percent != last_percent:
            last_percent = percent
            vram = (
                f" VRAM {update.vram_used_mb}/{update.vram_total_mb} MB"
                if update.vram_total_mb
                else ""
            )
            print(
                f"\r{percent:3d}% {update.message}{vram}",
                end="",
                flush=True,
                file=sys.stderr,
            )

    try:
        result = TranscriptionProcessor().run(
            arguments.input,
            options,
            cancel_event,
            progress,
        )
        print(file=sys.stderr)
        print("Exporting files…", file=sys.stderr)
        created = export_result(result, arguments.output, formats)
        for path in created:
            print(path.resolve())
        decisions = result.fallback_config.get("decisions", [])
        if decisions:
            print("Fallback decisions:", file=sys.stderr)
            for decision in decisions:
                print(f"- {decision}", file=sys.stderr)
        return 0
    except KeyboardInterrupt:
        cancel_event.set()
        print("\nCancellation requested.", file=sys.stderr)
        return 130
    except ProcessingCancelled:
        print("\nProcessing cancelled.", file=sys.stderr)
        return 130
    except (SpeakerTranscriberError, ValueError, OSError) as exc:
        logger.error("%s", exc)
        print(f"\nError: {exc}", file=sys.stderr)
        return 1
    except Exception:
        logging.getLogger("speaker_transcriber").exception("Processing failed")
        print("\nProcessing failed. See the log for details.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
