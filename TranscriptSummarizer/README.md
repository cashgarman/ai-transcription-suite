# Transcript Requirements Summarizer

A Python application that analyzes transcripts and extracts key requirements or points, presented as a numbered list. It uses the Gemma3:1b model via Ollama for local processing. The application comes with both GUI and CLI interfaces.

## Features

- Summarize transcripts into structured requirements lists
- Modern dark-themed GUI for interactive use
- Command-line interface for batch processing and automation
- Local processing using Gemma3:1b via Ollama
- Thread-safe design to keep the UI responsive during processing

## Prerequisites

- Python 3.8 or higher
- [Ollama](https://ollama.ai/) installed and running
- Gemma3:1b model available in Ollama (will be automatically pulled if missing)

### Installing Ollama

1. Download and install Ollama from [https://ollama.ai/download](https://ollama.ai/download)
2. Run Ollama (it needs to be running in the background when using this application)

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
pip install customtkinter ollama
```

## Usage

### GUI Application

1. Run the application using one of these methods:

```
# Using Python directly (requires activating the virtual environment first)
python summarize_gui.py

# Using the batch file (automatically activates the virtual environment)
summarize_gui.bat
```

2. Use the application:
   - Enter text directly or click "Load Transcript" to load a text file
   - Click "Summarize" to process the transcript
   - View the generated requirements list in the output area

### Command Line Interface

The application can also be used from the command line:

```
# Using Python directly (requires activating the virtual environment first)
python summarize.py input_file [--output OUTPUT_FILE] [--max-tokens MAX_TOKENS]

# Using the batch file (automatically activates the virtual environment)
summarize.bat input_file [--output OUTPUT_FILE] [--max-tokens MAX_TOKENS]
```

Arguments:
- `input_file`: Path to the transcript file to summarize (required)
- `--output`: Path to save the summary (optional, prints to console if not specified)
- `--max-tokens`: Maximum tokens for the summary (default: 2048)

Examples:
```
# Summarize a transcript and print to console
summarize.bat my_transcript.txt

# Summarize a transcript and save to a file
summarize.bat my_transcript.txt --output requirements.txt

# Customize the maximum tokens for the summary
summarize.bat my_transcript.txt --max-tokens 1024
```

## Structure

- `/src` - Core application source code
- `/Transcriber` - The original audio/video transcription tool

## Notes

- The first run will download the Gemma3:1b model if it's not already available in Ollama
- Summarization quality depends on the clarity and structure of the input transcript
- For best results, ensure Ollama is running with adequate resources (especially for longer transcripts)

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [Ollama](https://ollama.ai/) for local AI model serving
- [Gemma3](https://ai.google.dev/gemma) from Google for the underlying language model
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) for the modern UI 