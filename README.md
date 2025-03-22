# AI Transcription & Analysis Suite

This repository contains two complementary tools for audio/video transcription and requirements analysis:

## 1. Whisper AI Transcriber

A Python desktop application that converts MP4 or MP3 files into text transcripts using the Whisper AI model running locally on your machine.

- Located in the `/Transcriber` directory
- Transcribes audio and video files to text using Whisper AI
- Includes both GUI and CLI interfaces
- Supports GPU acceleration when available

See [Transcriber README](./Transcriber/README.md) for detailed information.

## 2. Transcript Requirements Summarizer

A Python application that analyzes transcripts and extracts key requirements or points, presented as a numbered list.

- Located in the `/TranscriptSummarizer` directory
- Uses Gemma3:1b model via Ollama for local processing
- Includes both GUI and CLI interfaces
- Perfect for analyzing meeting transcripts and identifying requirements

See [Summarizer README](./TranscriptSummarizer/README.md) for detailed information.

## Workflow Integration

These tools are designed to work together in a seamless workflow:

1. Use the Whisper AI Transcriber to convert audio/video recordings into text transcripts
2. Use the Transcript Requirements Summarizer to extract key points and requirements from those transcripts

This combination is perfect for:
- Converting meeting recordings into actionable requirements
- Extracting key points from interviews
- Summarizing lectures or presentations
- Creating documentation from verbal discussions

## Getting Started

Each tool has its own virtual environment and dependencies. Please refer to the README in each directory for setup and usage instructions. 