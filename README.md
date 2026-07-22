# Transcript Requirements Summarizer

A Python application that transcribes MP4 videos and produces detailed Markdown summaries of conversations using local AI. Summarization uses Qwen 3.5 9B via Ollama (~7 GB VRAM). Transcription uses OpenAI Whisper locally.

## Features

- Summarize transcripts into detailed Markdown documents that preserve conversation details
- Transcribe MP4 videos to text using local Whisper (GPU-accelerated when CUDA is available)
- Select video via file browser or drag-and-drop onto the input area
- Choose Whisper model quality (tiny through large) before transcribing
- Progress bar with elapsed time, estimated time remaining, and verbose log output
- Working cancel button during video transcription
- Modern dark-themed GUI for interactive use
- Local processing — no cloud APIs required
- Thread-safe design to keep the UI responsive during processing

## Prerequisites

- Python 3.8 or higher
- [Ollama](https://ollama.ai/) installed and running (for summarization)
- [ffmpeg](https://ffmpeg.org/download.html) installed and available on your `PATH` (for video audio extraction)
- Qwen 3.5 9B (`qwen3.5:9b`) via Ollama for summarization (~7 GB VRAM; fits 10 GB GPUs)
- Optional but recommended: NVIDIA GPU with CUDA for faster Whisper transcription

### Installing Ollama

1. Download and install Ollama from [https://ollama.ai/download](https://ollama.ai/download)
2. Run Ollama (it needs to be running in the background when using summarization)

### Installing ffmpeg

1. Download ffmpeg from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)
2. Ensure `ffmpeg` and `ffprobe` are on your system `PATH`
3. Verify with: `ffmpeg -version`

### GPU acceleration (optional)

Whisper uses PyTorch and will automatically use CUDA when available. For NVIDIA GPUs, install a CUDA-enabled PyTorch build after the base requirements:

```
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

If CUDA is not available, transcription falls back to CPU with a warning in the log.

## Installation

1. Clone or download this repository
2. Navigate to the project directory
3. Set up a virtual environment (optional but recommended):

```
python -m venv venv_summarizer
```

4. Activate the virtual environment:
   - Windows: `.\venv_summarizer\Scripts\activate`
   - macOS/Linux: `source venv_summarizer/bin/activate`

5. Install the required packages:

```
pip install -r requirements.txt
```

6. (Optional) Install CUDA-enabled PyTorch for GPU transcription — see above.

## Usage

1. Run the application using one of these methods:

```
# Using Python directly (requires activating the virtual environment first)
python summarize_gui.py

# Using the batch file (automatically activates the virtual environment)
summarize_gui.bat
```

2. Use the application:

**Transcribe a video:**
- Choose a Whisper model from the dropdown (smaller = faster, larger = more accurate)
- Click **Select Video** or drag-and-drop an `.mp4` onto the input area
- Click **Transcribe Video** to extract audio and run speech-to-text
- Watch the progress bar, elapsed/remaining time, and log output
- Click **Cancel** to stop an in-progress transcription
- The transcript appears in the Input Transcript text box when complete

**Summarize a transcript:**
- Enter text directly, load a `.txt` file, or transcribe a video first
- Click **Summarize** to produce a detailed Markdown summary of the conversation
- View the generated Markdown in the output area

A sample transcript is included in `example_transcript.txt` for testing.

## Structure

- `summarize_gui.py` - Application entry point
- `src/summarizer.py` - GUI and summarization logic
- `src/transcription.py` - Whisper transcription engine (chunked, GPU-aware)
- `logs/transcription.log` - Verbose transcription log (created at runtime)
- `example_transcript.txt` - Sample transcript for testing

## Notes

- The first Whisper run downloads model weights (~75 MB to ~3 GB depending on model size)
- Long videos are processed in 10-minute chunks to support cancellation and reduce memory use
- The first Ollama run downloads the `qwen3.5:9b` model if it is not already available (~6.6 GB)
- Long transcripts are summarized in chunks and merged to preserve detail across the full conversation

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [Ollama](https://ollama.ai/) for local AI model serving
- [Qwen](https://github.com/QwenLM) for the summarization model
- [OpenAI Whisper](https://github.com/openai/whisper) for local speech-to-text
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) for the modern UI
