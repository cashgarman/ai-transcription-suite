from speaker_transcriber.ui.progress_tooltips import (
    KEEP_COLUMN_KEYS,
    progress_column,
    progress_key,
    tooltip_for_progress,
)


def test_pipeline_stages_have_detailed_tooltips() -> None:
    transcribing = tooltip_for_progress("transcribing", "Transcribing speech")
    assert "speech into text" in transcribing.lower()
    assert "percentage" in transcribing.lower()

    diarizing = tooltip_for_progress("diarizing", "Identifying speaker turns")
    assert "who spoke" in diarizing.lower()

    extracting = tooltip_for_progress("extracting_audio", "Extracting mono 16 kHz audio")
    assert "16 kHz" in extracting
    ready_transcript = tooltip_for_progress("formatting", "Transcript ready")
    assert "paragraphs" in ready_transcript.lower()


def test_message_overrides_generic_stage() -> None:
    caching = tooltip_for_progress("loading_media", "Caching pyannote diarization models")
    inspecting = tooltip_for_progress("loading_media", "Inspecting media file")
    assert "pyannote" in caching.lower()
    assert "checking" in inspecting.lower()
    assert caching != inspecting


def test_summary_and_idle_messages() -> None:
    assert "sections" in tooltip_for_progress(None, "Summarizing section 2 of 5…").lower()
    assert "merged" in tooltip_for_progress(None, "Merging summaries (round 1, batch 1 of 2)…").lower()
    assert "compared" in tooltip_for_progress(None, "Validating summary against section extracts…").lower()
    assert "pdf" in tooltip_for_progress(None, "Writing PDF…").lower()
    assert "saved transcript" in tooltip_for_progress(None, "Loaded from cache").lower()
    assert "nothing is running" in tooltip_for_progress(None, "Ready").lower()
    assert "went wrong" in tooltip_for_progress(None, "Processing failed").lower()
    assert "went wrong" in tooltip_for_progress(None, "PDF export failed").lower()
    assert "finished" in tooltip_for_progress(None, "PDF export complete").lower()
    assert "formats you selected" in tooltip_for_progress(None, "Export complete").lower()


def test_progress_column_follows_pipeline_then_clears() -> None:
    assert progress_column("transcribing", "Transcribing speech") == "transcribe"
    assert progress_column("aligning", "Aligning word timestamps") == "align"
    assert progress_column("diarizing", "Identifying speaker turns") == "diarize"
    assert progress_column("assigning_speakers", "Assigning words to speakers") == "diarize"
    assert progress_column(None, "Summarizing section 1 of 3…") == "summarize"
    assert progress_column(None, "Writing PDF…") == "pdf"
    assert progress_column(None, "Complete — distil-large-v3, batch 4") is None
    assert progress_column(None, "Ready") is None
    assert progress_key(None, "Cancellation requested; waiting for a safe boundary…") in KEEP_COLUMN_KEYS
    assert progress_column(None, "Cancellation requested; waiting for a safe boundary…") is None
