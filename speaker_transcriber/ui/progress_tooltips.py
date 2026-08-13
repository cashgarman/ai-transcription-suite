from __future__ import annotations


TOOLTIPS: dict[str, str] = {
    "idle": (
        "Nothing is running right now.\n\n"
        "Add an audio or video file and click Start to transcribe it on this computer."
    ),
    "loading_models": (
        "Preparing speaker-detection models.\n\n"
        "The app is downloading or loading the pyannote models that later decide "
        "who spoke when. The first run (or a newly chosen model) can take a while; "
        "later runs reuse the files saved on this computer."
    ),
    "inspecting": (
        "Checking the media file.\n\n"
        "The app is reading the audio or video so it knows the length, format, and "
        "whether the file can be processed. If you added several files, it checks "
        "each one before combining them."
    ),
    "loading_media": (
        "Getting the media ready.\n\n"
        "The app is checking your file and making sure the speaker-detection models "
        "are available before it starts converting audio."
    ),
    "extracting_audio": (
        "Preparing a clean audio track.\n\n"
        "The file is being converted to a single microphone-style track at 16 kHz, "
        "which is what the speech models expect. Video picture is ignored. If you "
        "queued more than one file, they are merged in order first."
    ),
    "loading_whisper": (
        "Loading the speech-recognition model.\n\n"
        "Whisper (the model that turns speech into text) is being loaded into memory, "
        "and onto the GPU if you chose CUDA. Larger models take longer to load and "
        "use more memory."
    ),
    "transcribing": (
        "Turning speech into text.\n\n"
        "The recognizer is listening through the recording and writing down what it "
        "hears. The percentage next to this label is how far through this stage it "
        "has gotten, not the whole job."
    ),
    "aligning": (
        "Lining up each word with the audio.\n\n"
        "A second model is matching every transcribed word to the exact moment it "
        "was spoken, so you can click a word and jump to that time. If this step "
        "fails, the transcript is kept with coarser phrase-level times."
    ),
    "diarizing": (
        "Figuring out who spoke when.\n\n"
        "The app is grouping similar voices into speaker turns (for example "
        "SPEAKER_00 and SPEAKER_01). Names are generic until you rename them. "
        "This step needs a Hugging Face token and can fall back to CPU if the GPU "
        "runs out of memory."
    ),
    "assigning_speakers": (
        "Attaching speakers to each word.\n\n"
        "Speaker turns from the previous step are being matched to the timed words "
        "in the transcript, so each line can show who said it."
    ),
    "formatting": (
        "Building the readable transcript.\n\n"
        "Words are being grouped into paragraphs and given display names such as "
        "Speaker 1 and Speaker 2. After this, the transcript appears in the panel "
        "below."
    ),
    "summarizing": (
        "Writing a meeting summary.\n\n"
        "A local language model (Ollama) is reading the transcript in sections and "
        "drafting notes. Nothing is sent to the cloud. Long recordings are split "
        "so the model can fit them in memory."
    ),
    "merging_summary": (
        "Combining section summaries.\n\n"
        "The model summarized the recording in pieces. Those pieces are now being "
        "merged into one set of meeting notes so the story stays in order."
    ),
    "validating": (
        "Checking the summary against the section extracts.\n\n"
        "The draft notes are being compared with the extracted facts from the "
        "transcript so important points are less likely to be dropped or invented."
    ),
    "formatting_notes": (
        "Cleaning up the meeting notes.\n\n"
        "Headings, lists, and wording are being normalized so the summary is "
        "consistent before it is shown or written to a PDF."
    ),
    "writing_pdf": (
        "Creating the PDF file.\n\n"
        "The formatted meeting notes (and transcript, depending on the template) "
        "are being laid out and saved to the file you chose."
    ),
    "exporting": (
        "Saving the transcript to disk.\n\n"
        "The current transcript is being written in the formats you selected, "
        "such as text or JSON."
    ),
    "cancelling": (
        "Stopping at a safe point.\n\n"
        "Cancel was requested. The app is waiting until it can stop without "
        "losing the text it has already recognized. A partial transcript is kept "
        "when possible."
    ),
    "cancelled": (
        "The job was stopped.\n\n"
        "Processing did not finish. If any speech had already been recognized, "
        "that partial transcript is still available."
    ),
    "complete": (
        "Processing finished.\n\n"
        "The transcript is ready to search, rename speakers, summarize, or export. "
        "The details after the dash are the model and devices that were actually used."
    ),
    "cached": (
        "Loaded a saved transcript.\n\n"
        "This recording was processed earlier. The app reopened the saved result "
        "instead of running speech recognition again."
    ),
    "summary_complete": (
        "The summary is ready.\n\n"
        "The local language model finished writing meeting notes. You can edit "
        "them in the Summary tab or include them in a PDF."
    ),
    "failed": (
        "Something went wrong.\n\n"
        "The job stopped before it finished. Open the log at the bottom of the "
        "window for the error details."
    ),
}

_MESSAGE_KEYS: tuple[tuple[str, str], ...] = (
    ("caching pyannote", "loading_models"),
    ("inspecting media", "inspecting"),
    ("merging summaries", "merging_summary"),
    ("completed merge", "merging_summary"),
    ("summarizing section", "summarizing"),
    ("completed section", "summarizing"),
    ("starting summarization", "summarizing"),
    ("summarizing for pdf", "summarizing"),
    ("model reasoning", "summarizing"),
    ("validating summary", "validating"),
    ("checking extract", "validating"),
    ("applying validated", "validating"),
    ("missing facts", "validating"),
    ("formatting meeting", "formatting_notes"),
    ("formatting complete", "formatting_notes"),
    ("parsing meeting", "formatting_notes"),
    ("pdf export failed", "failed"),
    ("pdf export complete", "complete"),
    ("starting pdf", "writing_pdf"),
    ("writing pdf", "writing_pdf"),
    ("exporting files", "exporting"),
    ("export failed", "failed"),
    ("export complete", "exporting"),
    ("cancellation requested", "cancelling"),
    ("cancelled", "cancelled"),
    ("processing failed", "failed"),
    ("summary failed", "failed"),
    ("summary complete", "summary_complete"),
    ("complete —", "complete"),
    ("loaded from cache", "cached"),
)

COLUMN_FOR_KEY: dict[str, str | None] = {
    "idle": None,
    "loading_models": "transcribe",
    "inspecting": "transcribe",
    "loading_media": "transcribe",
    "extracting_audio": "transcribe",
    "loading_whisper": "transcribe",
    "transcribing": "transcribe",
    "aligning": "align",
    "diarizing": "diarize",
    "assigning_speakers": "diarize",
    "formatting": "diarize",
    "summarizing": "summarize",
    "merging_summary": "summarize",
    "validating": "summarize",
    "formatting_notes": "summarize",
    "writing_pdf": "pdf",
    "exporting": None,
    "cancelling": None,
    "cancelled": None,
    "complete": None,
    "cached": None,
    "summary_complete": None,
    "failed": None,
}

KEEP_COLUMN_KEYS = frozenset({"cancelling"})


def progress_key(stage: str | None, message: str = "") -> str:
    lowered = (message or "").strip().lower()
    if lowered == "ready":
        return "idle"
    for needle, key in _MESSAGE_KEYS:
        if needle in lowered:
            return key
    if stage and stage in TOOLTIPS:
        return stage
    return "idle"


def tooltip_for_progress(stage: str | None, message: str = "") -> str:
    """Return a plain-English explanation of the current progress phase."""
    return TOOLTIPS.get(progress_key(stage, message), TOOLTIPS["idle"])


def progress_column(stage: str | None, message: str = "") -> str | None:
    """Return the setup-column id to highlight, or None to clear it."""
    key = progress_key(stage, message)
    if key in KEEP_COLUMN_KEYS:
        return None
    return COLUMN_FOR_KEY.get(key)
