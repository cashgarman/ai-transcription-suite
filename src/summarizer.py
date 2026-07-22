import os
import sys
import argparse
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import threading
import time
import ollama

class RequirementsSummarizer:
    """Class to summarize transcripts into requirements lists using Gemma3:1b with Ollama"""
    
    def __init__(self):
        """Initialize the summarizer with Ollama client"""
        self.model_name = "gemma3:1b"
        self.client = ollama.Client()
        
        # Try to ensure the model is available
        try:
            self._ensure_model_available()
        except Exception as e:
            print(f"Warning: Could not verify model availability: {str(e)}")
    
    def _ensure_model_available(self):
        """Check if the model is available and pull it if not"""
        models = self.client.list()
        model_exists = any(model['name'] == self.model_name for model in models['models']) if 'models' in models else False
        
        if not model_exists:
            print(f"Model {self.model_name} not found. Pulling from Ollama...")
            self.client.pull(self.model_name)
    
    def summarize_text(self, text, max_tokens=2048):
        """Summarize text into a list of requirements"""
        if not text or text.strip() == "":
            return "Error: Empty input text provided."
        
        # Prepare the prompt
        prompt = f"""Please analyze the following transcript and extract a clear, concise list of requirements or key points. 
Format your response as a numbered list.

Transcript:
{text}

Requirements:"""
        
        try:
            # Generate the summary
            response = self.client.generate(
                model=self.model_name,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=0.2,  # Low temperature for more focused output
            )
            
            return response['response'].strip()
        except Exception as e:
            return f"Error generating summary: {str(e)}"

class SummarizerGUI:
    """GUI interface for the requirements summarizer"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Transcript Requirements Summarizer")
        self.root.geometry("1000x800")
        self.root.minsize(800, 600)
        
        # Set theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Initialize summarizer
        self.summarizer = RequirementsSummarizer()
        self.current_task = None
        
        # Configure grid
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_rowconfigure(2, weight=0)
        self.root.grid_rowconfigure(3, weight=1)
        self.root.grid_rowconfigure(4, weight=0)
        
        # Create widgets
        self.create_widgets()
    
    def create_widgets(self):
        # Title
        self.title_label = ctk.CTkLabel(self.root, text="Transcript Requirements Summarizer", 
                                        font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        
        # Input frame
        self.input_frame = ctk.CTkFrame(self.root)
        self.input_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        
        self.input_frame.grid_columnconfigure(0, weight=1)
        self.input_frame.grid_rowconfigure(0, weight=0)
        self.input_frame.grid_rowconfigure(1, weight=1)
        
        self.input_label = ctk.CTkLabel(self.input_frame, text="Input Transcript:", 
                                         font=ctk.CTkFont(size=16, weight="bold"))
        self.input_label.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="w")
        
        self.input_text = ctk.CTkTextbox(self.input_frame, wrap="word", height=200)
        self.input_text.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        
        # Button frame
        self.button_frame = ctk.CTkFrame(self.root)
        self.button_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        
        self.button_frame.grid_columnconfigure(0, weight=1)
        self.button_frame.grid_columnconfigure(1, weight=1)
        self.button_frame.grid_columnconfigure(2, weight=1)
        
        self.load_button = ctk.CTkButton(self.button_frame, text="Load Transcript", 
                                         command=self.load_file)
        self.load_button.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        
        self.summarize_button = ctk.CTkButton(self.button_frame, text="Summarize", 
                                              command=self.start_summarization)
        self.summarize_button.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        
        self.cancel_button = ctk.CTkButton(self.button_frame, text="Cancel", 
                                          command=self.cancel_operation,
                                          fg_color="transparent", border_width=2, 
                                          text_color=("gray10", "#DCE4EE"))
        self.cancel_button.grid(row=0, column=2, padx=10, pady=10, sticky="ew")
        
        # Output frame
        self.output_frame = ctk.CTkFrame(self.root)
        self.output_frame.grid(row=3, column=0, padx=20, pady=10, sticky="nsew")
        
        self.output_frame.grid_columnconfigure(0, weight=1)
        self.output_frame.grid_rowconfigure(0, weight=0)
        self.output_frame.grid_rowconfigure(1, weight=1)
        
        self.output_label = ctk.CTkLabel(self.output_frame, text="Requirements:", 
                                         font=ctk.CTkFont(size=16, weight="bold"))
        self.output_label.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="w")
        
        self.output_text = ctk.CTkTextbox(self.output_frame, wrap="word", height=200)
        self.output_text.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        
        # Status frame
        self.status_frame = ctk.CTkFrame(self.root)
        self.status_frame.grid(row=4, column=0, padx=20, pady=(10, 20), sticky="ew")
        
        self.status_label = ctk.CTkLabel(self.status_frame, text="Ready to summarize transcripts")
        self.status_label.pack(padx=10, pady=10)
    
    def load_file(self):
        """Load a transcript file"""
        file_path = filedialog.askopenfilename(
            title="Select Transcript File",
            filetypes=(
                ("Text Files", "*.txt"),
                ("All Files", "*.*")
            )
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    content = file.read()
                    self.input_text.delete("1.0", tk.END)
                    self.input_text.insert("1.0", content)
                self.status_label.configure(text=f"Loaded transcript from {os.path.basename(file_path)}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file: {str(e)}")
    
    def start_summarization(self):
        """Start summarization in a separate thread"""
        # Get the input text
        input_text = self.input_text.get("1.0", tk.END)
        
        if not input_text.strip():
            messagebox.showinfo("Information", "Please enter or load a transcript first.")
            return
        
        # Disable buttons during summarization
        self.summarize_button.configure(state="disabled")
        self.load_button.configure(state="disabled")
        
        # Update status
        self.status_label.configure(text="Summarizing transcript...")
        
        # Start the summarization in a separate thread
        self.current_task = threading.Thread(target=self.run_summarization, args=(input_text,))
        self.current_task.daemon = True
        self.current_task.start()
    
    def run_summarization(self, text):
        """Execute the summarization process"""
        try:
            # Generate the summary
            summary = self.summarizer.summarize_text(text)
            
            # Update the UI with the result
            self.root.after(0, self.update_output, summary)
        except Exception as e:
            self.root.after(0, self.show_error, str(e))
        finally:
            # Re-enable buttons
            self.root.after(0, self.reset_ui)
    
    def update_output(self, summary):
        """Update the output text box with the summary"""
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", summary)
        self.status_label.configure(text="Summarization complete")
    
    def show_error(self, error_message):
        """Show an error message"""
        messagebox.showerror("Error", error_message)
        self.status_label.configure(text=f"Error: {error_message}")
    
    def reset_ui(self):
        """Reset the UI state after processing"""
        self.summarize_button.configure(state="normal")
        self.load_button.configure(state="normal")
    
    def cancel_operation(self):
        """Cancel the current operation"""
        # Not much we can do to cancel Ollama mid-generation
        # But we can reset the UI
        self.status_label.configure(text="Operation canceled")
        self.reset_ui()

def gui_main():
    """Start the GUI application"""
    root = ctk.CTk()
    app = SummarizerGUI(root)
    root.mainloop()

def cli_main():
    """Run the CLI version of the summarizer"""
    parser = argparse.ArgumentParser(description="Summarize transcript into requirements list using Gemma3:1b")
    parser.add_argument("input_file", help="Path to the transcript file to summarize")
    parser.add_argument("--output", help="Output file path (default: print to console)")
    parser.add_argument("--max-tokens", type=int, default=2048, help="Maximum tokens for the summary (default: 2048)")
    
    args = parser.parse_args()
    
    # Check if input file exists
    if not os.path.exists(args.input_file):
        print(f"Error: File '{args.input_file}' not found")
        return 1
    
    try:
        # Read the input file
        with open(args.input_file, 'r', encoding='utf-8') as file:
            text = file.read()
        
        print(f"Processing transcript from {args.input_file}...")
        
        # Initialize the summarizer and generate the summary
        summarizer = RequirementsSummarizer()
        summary = summarizer.summarize_text(text, args.max_tokens)
        
        # Output the summary
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as file:
                file.write(summary)
            print(f"Summary saved to {args.output}")
        else:
            print("\n--- Requirements Summary ---")
            print(summary)
            print("---------------------------\n")
        
        return 0
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1

if __name__ == "__main__":
    # Check if running in CLI mode
    if len(sys.argv) > 1:
        sys.exit(cli_main())
    else:
        # Run in GUI mode
        gui_main() 