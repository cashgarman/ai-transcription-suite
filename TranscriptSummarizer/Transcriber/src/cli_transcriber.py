import os
import sys
import tempfile
import argparse
import whisper
import torch
import ffmpeg
import warnings
from pathlib import Path

# Suppress PyTorch security warning about torch.load
warnings.filterwarnings("ignore", category=FutureWarning, module="torch.serialization")

def convert_to_wav(file_path):
    """Convert audio file to WAV format suitable for Whisper"""
    # Create temporary file
    fd, temp_path = tempfile.mkstemp(suffix='.wav')
    os.close(fd)
    
    try:
        # Convert using ffmpeg
        (
            ffmpeg
            .input(file_path)
            .output(temp_path, acodec='pcm_s16le', ar='16000', ac=1)
            .run(quiet=True, overwrite_output=True)
        )
        
        return temp_path
    except Exception as e:
        # Clean up and re-raise
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise Exception(f"Failed to convert file: {str(e)}")

def transcribe_audio(input_file, model_size="base", output_file=None):
    """Transcribe audio file using Whisper"""
    # Check if file exists
    if not os.path.exists(input_file):
        print(f"Error: File '{input_file}' not found")
        return None
    
    # Check if input file is supported
    ext = os.path.splitext(input_file)[1].lower()
    if ext not in ['.mp3', '.mp4', '.wav', '.m4a', '.mov', '.avi']:
        print(f"Error: Unsupported file format '{ext}'")
        return None
    
    # Check if CUDA is available
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        print(f"Loading {model_size} model on GPU...")
    else:
        print(f"Loading {model_size} model on CPU (GPU not available)...")
    
    # Load Whisper model
    try:
        model = whisper.load_model(model_size, device=device)
        
        if device == "cuda":
            print(f"Model loaded on GPU (CUDA)")
        else:
            print(f"Model loaded on CPU")
        
        # Convert file to temporary WAV if needed
        temp_file = None
        try:
            if not input_file.lower().endswith('.wav'):
                print(f"Converting {os.path.basename(input_file)} to WAV...")
                temp_file = convert_to_wav(input_file)
                audio_file = temp_file
            else:
                audio_file = input_file
            
            # Transcribe
            print(f"Transcribing {os.path.basename(input_file)}...")
            
            # Use fp16 if on GPU, fallback to fp32 on CPU
            use_fp16 = (device == "cuda")
            result = model.transcribe(audio_file, fp16=use_fp16)
            
            # Return the result
            return result["text"]
            
        finally:
            # Delete temp file if created
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
                    
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Transcribe audio files using Whisper AI")
    parser.add_argument("input_file", help="Path to the audio file to transcribe")
    parser.add_argument("--model", choices=["tiny", "base", "small", "medium", "large"], 
                        default="base", help="Whisper model size (default: base)")
    parser.add_argument("--output", help="Output file path (default: print to console)")
    
    args = parser.parse_args()
    
    # Transcribe the audio file
    transcription = transcribe_audio(args.input_file, args.model)
    
    if transcription:
        # Print transcription to console
        print("\n--- Transcription ---")
        print(transcription)
        print("--------------------\n")
        
        # Save to output file if specified
        if args.output:
            try:
                with open(args.output, 'w', encoding='utf-8') as f:
                    f.write(transcription)
                print(f"Transcription saved to {args.output}")
            except Exception as e:
                print(f"Error saving to output file: {str(e)}")

if __name__ == "__main__":
    main() 