export type Feature = {
  title: string;
  body: string;
  meta: string;
};

export const FEATURES: Feature[] = [
  {
    title: "Speakers, separated",
    body: "pyannote finds every turn in the conversation and Summit assigns each word to whoever said it. Overlapping speech is kept rather than flattened, and you rename SPEAKER_00 to Priya once for the whole transcript.",
    meta: "Diarization",
  },
  {
    title: "Timestamps you can trust",
    body: "WhisperX aligns the transcript against the waveform with a language-specific model, so every word carries its own start and end time. If alignment cannot map a language, Summit falls back to segment timing instead of failing.",
    meta: "Word-level alignment",
  },
  {
    title: "Notes that read like a person wrote them",
    body: "Point Summit at a local Ollama model and it drafts a full meeting document: overview, decisions, action items with owners, and detailed notes per segment. Twelve styles, from a board summary to a two-host recap script.",
    meta: "Local summarization",
  },
  {
    title: "Export into whatever you already use",
    body: "TXT, Markdown, JSON, SRT, WebVTT, and CSV, plus a typeset PDF in a light or dark theme. JSON keeps overlap and uncertainty metadata for anyone building on top of it.",
    meta: "Six formats plus PDF",
  },
  {
    title: "Drag the file in and walk away",
    body: "MP4, MKV, MOV, AVI, WebM, WAV, MP3, M4A, FLAC, OGG, Opus, and AAC. FFmpeg handles the conversion; you watch stage progress, elapsed time, and live VRAM instead of a spinner.",
    meta: "Any media FFmpeg reads",
  },
  {
    title: "It will not fall over on your GPU",
    body: "Models load one at a time and are unloaded between stages. If CUDA runs out of memory, Summit halves the batch, steps down to a smaller model, then moves alignment or diarization to the CPU, and tells you exactly what it did.",
    meta: "Automatic OOM recovery",
  },
  {
    title: "Built for long recordings",
    body: "Detachable tabs, full-text search, a speaker heatmap of the timeline, per-speaker filtering, and a recent files list. A three-hour deposition is as navigable as a ten-minute standup.",
    meta: "Workbench, not a text box",
  },
  {
    title: "Cancel without losing work",
    body: "Stop at any point and Summit finishes at the next safe boundary, killing FFmpeg immediately where it can. If transcription already finished, you keep the transcript.",
    meta: "Interruptible pipeline",
  },
];

export type PipelineStage = {
  step: string;
  title: string;
  body: string;
};

export const PIPELINE: PipelineStage[] = [
  {
    step: "01",
    title: "Decode",
    body: "FFmpeg converts your file to mono 16 kHz audio.",
  },
  {
    step: "02",
    title: "Transcribe",
    body: "faster-whisper runs the words through CTranslate2.",
  },
  {
    step: "03",
    title: "Align",
    body: "WhisperX pins each word to the waveform.",
  },
  {
    step: "04",
    title: "Diarize",
    body: "pyannote decides who was speaking when.",
  },
  {
    step: "05",
    title: "Write",
    body: "A local model turns the transcript into notes.",
  },
];

export type NoteStyle = {
  name: string;
  body: string;
};

/** Mirrors SUMMARY_STYLES in speaker_transcriber/prompts/__init__.py. */
export const NOTE_STYLES: NoteStyle[] = [
  { name: "Pure Transcription", body: "A readable, cleaned-up transcript with no summarizing at all." },
  { name: "Meeting Summary", body: "Overview, decisions, action items, and detailed notes." },
  { name: "Pitch Deck", body: "Slide-ready outline: problem, solution, proof, ask." },
  { name: "Internal Newsletter", body: "Candid team update with owners and shoutouts." },
  { name: "External Newsletter", body: "Polished customer-facing update with no internals." },
  { name: "Technical Meeting", body: "Decision record: problem, options, decision, consequences." },
  { name: "Art Meeting", body: "Notes focused on visual direction and asset feedback." },
  { name: "Design Meeting", body: "Notes focused on problem framing and what to prototype." },
  { name: "Business Meeting", body: "Notes focused on goals, numbers, and commercial decisions." },
  { name: "Casual Meeting", body: "The same facts as a meeting summary, told as a warm recap." },
  { name: "Stand-Up Meeting", body: "Per-person yesterday, today, blockers, plus team themes." },
  { name: "AI Voiced Dialogue", body: "A two-host recap script written to be read aloud." },
];

export type Audience = {
  eyebrow: string;
  title: string;
  body: string;
  points: string[];
};

export const AUDIENCES: Audience[] = [
  {
    eyebrow: "For businesses",
    title: "The recording never leaves the building",
    body: "Board meetings, performance reviews, patient intake, client privilege, incident calls. Summit gives you the transcript and the meeting notes without asking you to ship the audio to a vendor, sign a data processing agreement, or explain a third-party subprocessor to your compliance team.",
    points: [
      "No subprocessors to disclose and no retention policy to negotiate",
      "Runs on machines you already own, offline after setup",
      "Action items with named owners, exported as a PDF you can circulate",
      "One-time licensing instead of a per-seat subscription that grows with headcount",
    ],
  },
  {
    eyebrow: "For everyone else",
    title: "Your own words, on your own machine",
    body: "Podcast episodes, lecture recordings, research interviews, family history, the two hours of tape you keep meaning to write up. Drop the file in, get subtitles and a clean transcript back, and never wonder whether a stranger's model was trained on your voice.",
    points: [
      "Subtitle files that drop straight into a video editor",
      "Speaker names you set once and reuse across a series",
      "No monthly bill and no upload queue",
      "Works on a laptop with a mid-range NVIDIA card",
    ],
  },
];

export type Faq = {
  question: string;
  answer: string;
};

export const FAQS: Faq[] = [
  {
    question: "What does the free trial actually include?",
    answer:
      "Everything. Every Whisper model, speaker diarization, all six export formats, PDF notes, and all twelve notes styles. The trial transcribes one file at a time. Recordings longer than ten minutes can be transcribed for the first ten minutes; Personal unlocks the full recording and multi-file merge. Nothing is watermarked, nothing expires, and there is no account to create.",
  },
  {
    question: "What hardware do I need?",
    answer:
      "Windows 10/11 or Linux, an NVIDIA GPU with a current driver, and roughly 6 to 10 GB of VRAM depending on the model you pick. Models run one at a time, so those figures are not additive. CPU transcription works from the command line but is substantially slower.",
  },
  {
    question: "Is it really offline?",
    answer:
      "Your audio and transcripts never leave the computer, and Summit never sends content to an API. The internet is used once, to download model weights, and to authenticate with Hugging Face for the gated speaker model. After that you can pull the network cable.",
  },
  {
    question: "Why do I need a Hugging Face token?",
    answer:
      "The pyannote speaker-diarization model is gated by its authors, so downloading it requires a free read token and accepting their terms. Summit stores that token in your operating system credential store, keeps it out of the settings file, and redacts it from logs.",
  },
  {
    question: "Do I have to install anything else?",
    answer:
      "FFmpeg, which handles decoding, and a CUDA-enabled build of PyTorch. If you want AI-written meeting notes, install Ollama and pull a model such as Qwen; the notes feature is optional and the transcript works without it.",
  },
  {
    question: "Can Summit tell me who is speaking by name?",
    answer:
      "It tells you how many distinct voices there are and which one said what, labelled SPEAKER_00, SPEAKER_01, and so on. It does not match voices against enrolled identities. You rename the labels after processing and Summit applies those names everywhere.",
  },
  {
    question: "How accurate is speaker separation?",
    answer:
      "Very good on clean multi-microphone recordings, and honest about the rest. Similar voices, heavy crosstalk, short interjections, music, reverberation, and telephone audio all reduce accuracy. Overlapping turns are retained in the JSON export along with uncertainty metadata.",
  },
  {
    question: "Is there a macOS version?",
    answer:
      "Not yet. Summit targets Windows and Linux with NVIDIA hardware. Join the launch list if you want to be told when that changes.",
  },
];

export type PrivacyPoint = {
  title: string;
  body: string;
};

export const PRIVACY_POINTS: PrivacyPoint[] = [
  {
    title: "Decoding is local",
    body: "FFmpeg runs on your machine. The converted audio is a temporary file on your own disk.",
  },
  {
    title: "Inference is local",
    body: "Whisper, WhisperX, and pyannote all execute on your GPU. No inference API is contacted.",
  },
  {
    title: "Summarization is local",
    body: "Notes are written by an Ollama model running on the same computer, not by a hosted assistant.",
  },
  {
    title: "The network is optional",
    body: "Hugging Face is contacted only to authenticate and fetch model files. After that, Summit works offline.",
  },
];
