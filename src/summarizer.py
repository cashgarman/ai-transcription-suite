import logging
import os
import queue
import threading
import tkinter as tk
from logging.handlers import QueueHandler
from tkinter import filedialog, messagebox

import customtkinter as ctk
import ollama
from tkinterdnd2 import DND_FILES, TkinterDnD

from transcription import (
    ProgressUpdate,
    TranscriptionCancelled,
    WHISPER_MODELS,
    setup_file_logging,
    transcribe_video,
)


class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)


class RequirementsSummarizer:
    """Summarize transcripts into detailed Markdown using a local Ollama model."""

    MODEL_NAME = "qwen3.5:9b"
    CHUNK_CHAR_LIMIT = 3500
    MERGE_BATCH_SIZE = 3

    SYSTEM_PROMPT = """You are an expert analyst documenting conversations and meetings.

Your task is to produce thorough, faithful Markdown that captures the full substance of the transcript.

Rules:
- Output valid Markdown only.
- Preserve ALL substantive details: every topic discussed, decisions, requests, concerns, questions, answers, numbers, deadlines, names, roles, action items, constraints, and technical specifics.
- Do NOT over-summarize, omit topics, or replace specifics with vague bullets.
- Use clear structure with headings (##, ###), bullet lists, and tables where helpful.
- Attribute statements to speakers when the transcript identifies them.
- If something is unclear in the transcript, note the ambiguity rather than inventing details.
- Do not add information that is not supported by the transcript."""

    CHUNK_PROMPT = """Create a detailed Markdown write-up of this transcript segment. Include every topic and detail from the segment below.

Transcript segment:
{text}"""

    MERGE_PROMPT = """Combine the following Markdown section summaries into one cohesive, comprehensive Markdown document.

Requirements:
- Keep ALL details from every section. Do not drop topics, names, numbers, or decisions.
- Remove only redundant wrapper headings, not content.
- Use one top-level title (# ...) and logical ## / ### sections.
- Preserve speaker attributions, decisions, open questions, and action items.

Sections to merge:
{sections}"""

    def __init__(self):
        """Initialize the summarizer with Ollama client"""
        self.model_name = self.MODEL_NAME
        self.client = ollama.Client()

        try:
            self._ensure_model_available()
        except Exception as e:
            print(f"Warning: Could not verify model availability: {str(e)}")

    def _ensure_model_available(self):
        """Check if the model is available and pull it if not"""
        models = self.client.list()
        available_models = models.models if hasattr(models, "models") else models.get("models", [])
        model_exists = any(self._get_model_name(model) == self.model_name for model in available_models)

        if not model_exists:
            print(f"Model {self.model_name} not found. Pulling from Ollama...")
            self.client.pull(self.model_name)

    def _get_model_name(self, model_entry):
        if hasattr(model_entry, "model"):
            return model_entry.model
        if isinstance(model_entry, dict):
            return model_entry.get("model") or model_entry.get("name")
        return None

    def _split_into_chunks(self, text: str) -> list[str]:
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        if not paragraphs:
            return [text.strip()]

        chunks = []
        current = []

        for paragraph in paragraphs:
            candidate = "\n\n".join(current + [paragraph])
            if current and len(candidate) > self.CHUNK_CHAR_LIMIT:
                chunks.append("\n\n".join(current))
                current = [paragraph]
            else:
                current.append(paragraph)

        if current:
            chunks.append("\n\n".join(current))

        return chunks

    def _extract_response_text(self, response) -> str:
        if hasattr(response, "response"):
            return response.response.strip()
        return response["response"].strip()

    def _generate(self, prompt: str, num_predict: int = 4096) -> str:
        response = self.client.generate(
            model=self.model_name,
            system=self.SYSTEM_PROMPT,
            prompt=prompt,
            options={
                "num_predict": num_predict,
                "num_ctx": 8192,
                "temperature": 0.2,
            },
        )
        return self._extract_response_text(response)

    def _summarize_chunk(self, chunk_text: str) -> str:
        return self._generate(self.CHUNK_PROMPT.format(text=chunk_text), num_predict=4096)

    def _merge_sections(self, sections: list[str]) -> str:
        numbered_sections = []
        for index, section in enumerate(sections, start=1):
            numbered_sections.append(f"### Section {index}\n\n{section}")
        merged_input = "\n\n".join(numbered_sections)
        return self._generate(
            self.MERGE_PROMPT.format(sections=merged_input),
            num_predict=8192,
        )

    def _merge_in_batches(self, sections: list[str]) -> str:
        if len(sections) <= self.MERGE_BATCH_SIZE:
            return self._merge_sections(sections)

        batch_results = []
        for start in range(0, len(sections), self.MERGE_BATCH_SIZE):
            batch = sections[start:start + self.MERGE_BATCH_SIZE]
            batch_results.append(self._merge_sections(batch))

        if len(batch_results) == 1:
            return batch_results[0]

        return self._merge_sections(batch_results)

    def summarize_text(self, text, max_tokens=8192):
        """Summarize text into a detailed Markdown document."""
        if not text or text.strip() == "":
            return "Error: Empty input text provided."

        try:
            chunks = self._split_into_chunks(text.strip())
            if len(chunks) == 1:
                return self._generate(
                    self.CHUNK_PROMPT.format(text=chunks[0]),
                    num_predict=max_tokens,
                )

            section_summaries = [self._summarize_chunk(chunk) for chunk in chunks]
            return self._merge_in_batches(section_summaries)
        except Exception as e:
            return f"Error generating summary: {str(e)}"


class SummarizerGUI:
    """GUI interface for the requirements summarizer"""

    MODEL_LABELS = {
        "tiny": "tiny (fastest)",
        "base": "base (balanced)",
        "small": "small",
        "medium": "medium",
        "large": "large (most accurate)",
    }

    def __init__(self, root):
        self.root = root
        self.root.title("Transcript Requirements Summarizer")
        self.root.geometry("1000x900")
        self.root.minsize(800, 700)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.summarizer = RequirementsSummarizer()
        self.current_task = None
        self.active_operation = None
        self.cancel_event = threading.Event()
        self.selected_video_path = None
        self.whisper_model = tk.StringVar(value="base")
        self.log_queue = queue.Queue()

        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dir = os.path.join(script_dir, "logs")
        self.log_file_path = setup_file_logging(log_dir)
        self._setup_transcription_logging()

        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_rowconfigure(2, weight=0)
        self.root.grid_rowconfigure(3, weight=0)
        self.root.grid_rowconfigure(4, weight=1)
        self.root.grid_rowconfigure(5, weight=0)

        self.create_widgets()
        self._poll_log_queue()

    def _setup_transcription_logging(self):
        logger = logging.getLogger("transcriber")
        queue_handler = QueueHandler(self.log_queue)
        queue_handler.setLevel(logging.INFO)
        queue_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
        )
        logger.addHandler(queue_handler)

    def create_widgets(self):
        self.title_label = ctk.CTkLabel(
            self.root,
            text="Transcript Requirements Summarizer",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        self.title_label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")

        self.input_frame = ctk.CTkFrame(self.root)
        self.input_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        self.input_frame.grid_columnconfigure(0, weight=1)
        self.input_frame.grid_columnconfigure(1, weight=0)
        self.input_frame.grid_rowconfigure(2, weight=1)

        self.input_label = ctk.CTkLabel(
            self.input_frame,
            text="Input Transcript:",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.input_label.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="w")

        self.model_label = ctk.CTkLabel(
            self.input_frame,
            text="Whisper model:",
            font=ctk.CTkFont(size=14),
        )
        self.model_label.grid(row=0, column=1, padx=10, pady=(10, 0), sticky="e")

        self.model_menu = ctk.CTkOptionMenu(
            self.input_frame,
            values=[self.MODEL_LABELS[m] for m in WHISPER_MODELS],
            command=self._on_model_selected,
        )
        self.model_menu.set(self.MODEL_LABELS["base"])
        self.model_menu.grid(row=1, column=1, padx=10, pady=(0, 10), sticky="e")

        self.drop_hint_label = ctk.CTkLabel(
            self.input_frame,
            text="Drop an MP4 here or use Select Video below",
            font=ctk.CTkFont(size=12),
            text_color="gray70",
        )
        self.drop_hint_label.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="w")

        self.input_text = ctk.CTkTextbox(self.input_frame, wrap="word", height=200)
        self.input_text.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="nsew")

        self.input_frame.drop_target_register(DND_FILES)
        self.input_frame.dnd_bind("<<Drop>>", self.on_video_drop)

        self.button_frame = ctk.CTkFrame(self.root)
        self.button_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        for column in range(5):
            self.button_frame.grid_columnconfigure(column, weight=1)

        self.load_button = ctk.CTkButton(
            self.button_frame,
            text="Load Transcript",
            command=self.load_file,
        )
        self.load_button.grid(row=0, column=0, padx=5, pady=10, sticky="ew")

        self.select_video_button = ctk.CTkButton(
            self.button_frame,
            text="Select Video",
            command=self.select_video,
        )
        self.select_video_button.grid(row=0, column=1, padx=5, pady=10, sticky="ew")

        self.transcribe_button = ctk.CTkButton(
            self.button_frame,
            text="Transcribe Video",
            command=self.start_transcription,
            state="disabled",
        )
        self.transcribe_button.grid(row=0, column=2, padx=5, pady=10, sticky="ew")

        self.summarize_button = ctk.CTkButton(
            self.button_frame,
            text="Summarize",
            command=self.start_summarization,
        )
        self.summarize_button.grid(row=0, column=3, padx=5, pady=10, sticky="ew")

        self.cancel_button = ctk.CTkButton(
            self.button_frame,
            text="Cancel",
            command=self.cancel_operation,
            fg_color="transparent",
            border_width=2,
            text_color=("gray10", "#DCE4EE"),
        )
        self.cancel_button.grid(row=0, column=4, padx=5, pady=10, sticky="ew")

        self.progress_frame = ctk.CTkFrame(self.root)
        self.progress_frame.grid(row=3, column=0, padx=20, pady=(0, 10), sticky="ew")
        self.progress_frame.grid_columnconfigure(0, weight=1)
        self.progress_frame.grid_remove()

        self.progress_status_label = ctk.CTkLabel(
            self.progress_frame,
            text="Preparing transcription...",
            anchor="w",
        )
        self.progress_status_label.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.progress_bar.set(0)

        self.time_frame = ctk.CTkFrame(self.progress_frame, fg_color="transparent")
        self.time_frame.grid(row=2, column=0, padx=10, pady=(0, 5), sticky="ew")
        self.time_frame.grid_columnconfigure(0, weight=1)
        self.time_frame.grid_columnconfigure(1, weight=1)

        self.elapsed_label = ctk.CTkLabel(self.time_frame, text="Elapsed: 0:00", anchor="w")
        self.elapsed_label.grid(row=0, column=0, sticky="w")

        self.eta_label = ctk.CTkLabel(self.time_frame, text="Remaining: --", anchor="e")
        self.eta_label.grid(row=0, column=1, sticky="e")

        self.log_label = ctk.CTkLabel(
            self.progress_frame,
            text="Transcription log:",
            anchor="w",
        )
        self.log_label.grid(row=3, column=0, padx=10, pady=(5, 0), sticky="ew")

        self.log_text = ctk.CTkTextbox(self.progress_frame, wrap="word", height=120)
        self.log_text.grid(row=4, column=0, padx=10, pady=(5, 10), sticky="ew")
        self.log_text.configure(state="disabled")

        self.output_frame = ctk.CTkFrame(self.root)
        self.output_frame.grid(row=4, column=0, padx=20, pady=10, sticky="nsew")
        self.output_frame.grid_columnconfigure(0, weight=1)
        self.output_frame.grid_rowconfigure(1, weight=1)

        self.output_label = ctk.CTkLabel(
            self.output_frame,
            text="Markdown Summary:",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.output_label.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="w")

        self.output_text = ctk.CTkTextbox(self.output_frame, wrap="word", height=200)
        self.output_text.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        self.status_frame = ctk.CTkFrame(self.root)
        self.status_frame.grid(row=5, column=0, padx=20, pady=(10, 20), sticky="ew")

        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="Ready to summarize transcripts",
        )
        self.status_label.pack(padx=10, pady=10)

    def _on_model_selected(self, label: str):
        for model, model_label in self.MODEL_LABELS.items():
            if model_label == label:
                self.whisper_model.set(model)
                break

    def _poll_log_queue(self):
        while not self.log_queue.empty():
            record = self.log_queue.get_nowait()
            self.log_text.configure(state="normal")
            self.log_text.insert("end", record.getMessage() + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(100, self._poll_log_queue)

    def _parse_dropped_path(self, data: str) -> str:
        data = data.strip()
        if data.startswith("{") and "}" in data:
            return data[1:data.index("}")]
        return data.split()[0] if data else ""

    def _set_selected_video(self, file_path: str):
        if not file_path.lower().endswith(".mp4"):
            messagebox.showerror("Error", "Only .mp4 video files are supported.")
            return

        if not os.path.exists(file_path):
            messagebox.showerror("Error", f"File not found: {file_path}")
            return

        self.selected_video_path = file_path
        self.transcribe_button.configure(state="normal")
        self.status_label.configure(
            text=f"Ready — selected: {os.path.basename(file_path)}"
        )

    def on_video_drop(self, event):
        if self.active_operation:
            return

        first_path = self._parse_dropped_path(event.data or "")
        self._set_selected_video(first_path)

    def select_video(self):
        if self.active_operation:
            return

        file_path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=(
                ("MP4 Video", "*.mp4"),
                ("All Files", "*.*"),
            ),
        )
        if file_path:
            self._set_selected_video(file_path)

    def load_file(self):
        """Load a transcript file"""
        if self.active_operation:
            return

        file_path = filedialog.askopenfilename(
            title="Select Transcript File",
            filetypes=(
                ("Text Files", "*.txt"),
                ("All Files", "*.*"),
            ),
        )

        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    content = file.read()
                    self.input_text.delete("1.0", tk.END)
                    self.input_text.insert("1.0", content)
                self.status_label.configure(
                    text=f"Loaded transcript from {os.path.basename(file_path)}"
                )
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file: {str(e)}")

    def _set_buttons_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.load_button.configure(state=state)
        self.select_video_button.configure(state=state)
        self.summarize_button.configure(state=state)
        self.model_menu.configure(state=state)
        if enabled:
            transcribe_state = "normal" if self.selected_video_path else "disabled"
            self.transcribe_button.configure(state=transcribe_state)
        else:
            self.transcribe_button.configure(state="disabled")

    def _show_progress_panel(self):
        self.progress_frame.grid()
        self.progress_bar.set(0)
        self.progress_status_label.configure(text="Preparing transcription...")
        self.elapsed_label.configure(text="Elapsed: 0:00")
        self.eta_label.configure(text="Remaining: --")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state="disabled")

    def _hide_progress_panel(self):
        self.progress_frame.grid_remove()

    def _format_duration(self, seconds: float) -> str:
        total_seconds = max(0, int(seconds))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    def _update_progress(self, update: ProgressUpdate):
        self.progress_bar.set(update.progress)
        self.progress_status_label.configure(text=update.message)
        self.elapsed_label.configure(text=f"Elapsed: {self._format_duration(update.elapsed_sec)}")
        if update.eta_sec is None:
            self.eta_label.configure(text="Remaining: --")
        else:
            self.eta_label.configure(
                text=f"Remaining: ~{self._format_duration(update.eta_sec)}"
            )

    def start_transcription(self):
        if self.active_operation:
            return

        if not self.selected_video_path:
            messagebox.showinfo("Information", "Please select or drop an MP4 video first.")
            return

        self.cancel_event.clear()
        self.active_operation = "transcribe"
        self._set_buttons_enabled(False)
        self._show_progress_panel()
        self.status_label.configure(text="Transcribing video...")

        model_size = self.whisper_model.get()
        video_path = self.selected_video_path

        self.current_task = threading.Thread(
            target=self.run_transcription,
            args=(video_path, model_size),
            daemon=True,
        )
        self.current_task.start()

    def run_transcription(self, video_path: str, model_size: str):
        try:
            def on_progress(update: ProgressUpdate):
                self.root.after(0, self._update_progress, update)

            transcript = transcribe_video(
                video_path,
                model_size,
                cancel_event=self.cancel_event,
                on_progress=on_progress,
            )
            self.root.after(0, self._fill_input_text, transcript)
            self.root.after(0, self._set_status, "Transcription complete")
        except TranscriptionCancelled:
            self.root.after(0, self._set_status, "Transcription cancelled")
        except Exception as e:
            self.root.after(0, self.show_error, str(e))
        finally:
            self.root.after(0, self.reset_ui)

    def _fill_input_text(self, text: str):
        self.input_text.delete("1.0", tk.END)
        self.input_text.insert("1.0", text)

    def _set_status(self, message: str):
        self.status_label.configure(text=message)

    def start_summarization(self):
        """Start summarization in a separate thread"""
        if self.active_operation:
            return

        input_text = self.input_text.get("1.0", tk.END)

        if not input_text.strip():
            messagebox.showinfo("Information", "Please enter or load a transcript first.")
            return

        self.active_operation = "summarize"
        self._set_buttons_enabled(False)
        self.status_label.configure(text="Summarizing transcript...")

        self.current_task = threading.Thread(
            target=self.run_summarization,
            args=(input_text,),
            daemon=True,
        )
        self.current_task.daemon = True
        self.current_task.start()

    def run_summarization(self, text):
        """Execute the summarization process"""
        try:
            summary = self.summarizer.summarize_text(text)
            self.root.after(0, self.update_output, summary)
        except Exception as e:
            self.root.after(0, self.show_error, str(e))
        finally:
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
        self.active_operation = None
        self.cancel_event.clear()
        self._hide_progress_panel()
        self._set_buttons_enabled(True)

    def cancel_operation(self):
        """Cancel the current operation"""
        if self.active_operation == "transcribe":
            self.cancel_event.set()
            self.status_label.configure(text="Cancelling transcription...")
            logging.getLogger("transcriber").info("Cancellation requested by user.")
            return

        if self.active_operation == "summarize":
            logging.getLogger("transcriber").info(
                "Summarization cancel requested (Ollama cannot be interrupted mid-generation)."
            )
            self.status_label.configure(text="Operation canceled")
            self.reset_ui()
            return

        self.status_label.configure(text="No active operation to cancel")


def gui_main():
    """Start the GUI application"""
    root = DnDCTk()
    SummarizerGUI(root)
    root.mainloop()
