# Whisper AI Transcriber

A Python desktop application that converts MP4 or MP3 files into text transcripts using OpenAI's Whisper AI model running locally on your machine.

## Features

- Transcribe audio and video files (MP3, MP4, WAV, M4A, MOV, AVI) to text
- Simple drag & drop interface
- Modern dark-themed GUI
- Progress tracking for batch processing
- Select from multiple Whisper model sizes (tiny, base, small, medium, large)
- Local processing - no internet required, runs completely on your machine
- GPU acceleration support for faster transcription (if CUDA available)
- Command-line interface (CLI) for batch processing and automation

## Usage

### GUI Application

1. Run the application using one of these methods:

```
# Using Python directly (requires activating the virtual environment first)
python transcriber_launcher.py

# Using the batch file (automatically activates the virtual environment)
transcriber.bat
```

2. Use the application:
   - Drag and drop audio/video files onto the application window
   - Or click "Select Files" to browse for files
   - Choose your preferred Whisper model size (smaller = faster, larger = more accurate)
   - Click "Transcribe" to begin the process
   - Transcripts will be saved to the "output" folder

### Command Line Interface

The application can also be used from the command line without a GUI:

```
# Using Python directly (requires activating the virtual environment first)
python transcribe.py input_file [--model MODEL] [--output OUTPUT_FILE]

# Using the batch file (automatically activates the virtual environment)
transcribe.bat input_file [--model MODEL] [--output OUTPUT_FILE]
```

Arguments:
- `input_file`: Path to the audio file to transcribe (required)
- `--model`: Whisper model size to use (choices: tiny, base, small, medium, large; default: base)
- `--output`: Path to save the transcription (optional, prints to console if not specified)

Examples:
```
# Transcribe an audio file and print to console
transcribe.bat my_audio.mp3

# Transcribe using the small model and save to a file
transcribe.bat my_audio.mp3 --model small --output my_transcript.txt
``` 