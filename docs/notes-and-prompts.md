# Meeting notes and prompts

The second pipeline takes a finished transcript and writes a document from it
using a local language model served by Ollama. It is independent of
transcription: it runs on demand, from cached transcripts as well as fresh ones,
and its failures never affect the transcript.

The code lives in `speaker_transcriber/models/summarization.py` (the
orchestrator), `notes_assembly.py` (deterministic merging), `section_filter.py`
(post-processing), and `speaker_transcriber/prompts/` (the style registry and
prompt text).

## Why it is built this way

A meeting transcript is far longer than any practical context window, so the
transcript has to be chunked and the chunk outputs recombined. The naive
approach — summarise each chunk, concatenate — loses cross-chunk structure. The
approach here separates two jobs: the model extracts detailed notes per chunk,
and then a second pass writes only the *front matter* (the executive summary,
decisions, action items) from those extracts. The detailed per-topic notes are
merged deterministically in Python rather than by the model, because merging
text is a job code does reliably and models do lossily.

Three pipeline modes fall out of this, declared per style:

| Pipeline | What the merge pass produces | What is appended |
|---|---|---|
| `meeting` | Front matter only | Detailed notes, assembled by `assemble_notes()` |
| `document` | The entire document | Nothing |
| `sequential` | No merge pass at all | Extracts concatenated in order |

`meeting` suits meeting notes, where an overview sits above a full record.
`document` suits shorter derived artefacts — a pitch deck, a newsletter, a
decision record — where the whole point is compression. `sequential` suits
outputs that must preserve the transcript's order and length, namely the cleaned
transcript and the two-host dialogue script.

## The flow

`RequirementsSummarizer.summarize()` is the entry point.

```
summarize(text)
  ├─ _chunks(text)                       split the transcript
  ├─ for each chunk                      extract stage, 0 → 55 %
  │    ├─ _chunk_prompt(chunk, running, is_last)
  │    ├─ _generate_stream(..., "extract")
  │    ├─ _ensure_complete(...)          continue if truncated
  │    └─ _running_outline(extracts)     rolling context for the next chunk
  │
  ├─ if pipeline is sequential → join extracts and return
  │
  ├─ _front_matter(extracts)             merge stage, 55 → 80 %
  ├─ _validate(front_matter, extracts)   optional, budget permitting
  ├─ _assemble_document(...)             append notes, reorder trailing sections
  └─ _strip_excluded(...)                remove user-disabled sections
```

### Chunking

There is no fixed chunk size. Every budget is derived from the context length
the user selected, because that is the only number that actually constrains the
model. The constants are at the top of `summarization.py`:

| Constant | Value | Role |
|---|---|---|
| `CHARS_PER_TOKEN` | 4 | Token estimation; no tokeniser is loaded |
| `CHUNK_BUDGET_FRACTION` | 0.60 | Ceiling on transcript text per prompt |
| `STATE_CARD_FRACTION` | 0.18 | Budget for the rolling outline |
| `PROMPT_OVERHEAD_FRACTION` | 0.08 | Reserved for the prompt wrapper |
| `MIN_CHUNK_FRACTION` | 0.25 | Floor, so chunks never become tiny |
| `MAX_CONTINUE_PASSES` | 2 | Continuation attempts per generation |
| `TRUNCATION_CAP_RATIO` | 0.90 | Output length that counts as "probably cut off" |

`_chunk_char_limit()` combines these into a character budget.
`_prompt_char_budget(stage)` computes `(num_ctx − num_predict) × 4`, where
`num_predict` is a per-stage fraction of the context: 0.35 for extraction, 0.30
for merge and validate, 0.70 for format and continuation.

Text is split on blank lines into paragraphs, oversized paragraphs are broken at
sentence boundaries (and, failing that, at character positions), and paragraphs
are packed greedily into chunks.

### The rolling outline

Each chunk prompt after the first includes a compressed record of what has
already been captured, under the heading `## Already recorded, background only`.
It is built by `_running_outline()` from `topic_titles()` and `recent_lines()`
in `notes_assembly.py`, and trimmed to the state-card budget.

This is what stops the model reintroducing the same decision in every chunk. It
is explicitly labelled background so the model does not re-summarise it.

Each chunk also ends with a marker — `[MORE SEGMENTS FOLLOW]` or
`[END OF TRANSCRIPT]` — so the model knows whether it is allowed to write a
conclusion. The system prompts explain these markers.

### Merging

`_front_matter()` handles one extract with a single `_merge()` call. With
several, it merges hierarchically: `_pack_groups()` batches extracts to fit the
merge budget, each batch is merged, and the process repeats until one section
remains.

### Validation

`_validate()` sends the draft plus the extracts back to the model to check the
overview against the source. It runs only if the whole payload fits the validate
budget, which for long meetings it often does not — in that case it is skipped
and logged. The result is rejected if it comes back empty or shorter than 60 %
of the draft, on the assumption that the model dropped content rather than
tightened it.

### Continuation

`_looks_truncated()` flags an output that is close to the `num_predict` ceiling,
ends mid-sentence, or (for merge and validate) is missing the style's
`required_sections`. `_ensure_complete()` then sends the shared
`prompts/continue.txt` prompt with the document tail, up to twice.

### Deterministic assembly

For `meeting` styles, `assemble_notes(front_matter, extracts)` in
`notes_assembly.py` appends the detailed notes. It parses each extract into
heading-delimited blocks, normalises and matches topic titles across chunks so
the same topic discussed twice merges into one section, and drops lines already
covered elsewhere using a line index and a coverage index built from significant
tokens. Placeholder content is discarded.

Finally `move_sections_to_end()` relocates sections listed in the style's
`trailing_sections` — for meeting styles, "Closing Assessment" — so they land
after the appended notes rather than in the middle of the document.

## The prompt system

`speaker_transcriber/prompts/__init__.py` is both the style registry and the
prompt loader.

### Loading and caching

Each style is a directory under `prompts/styles/<style_id>/` containing exactly
five files:

| File | Used at | Purpose |
|---|---|---|
| `system.txt` | every call | Persona, global rules, marker semantics |
| `chunk.txt` | extract | How to take notes on one transcript segment |
| `merge.txt` | merge | How to combine extracts |
| `validate.txt` | validate | How to check the draft against extracts |
| `format.txt` | format | Formatting-only pass, no summarising |

One shared file, `prompts/continue.txt`, handles truncated generations for all
styles.

`load_prompts()` reads every file and raises `FileNotFoundError` if any is
missing or empty, so a broken prompt pack fails at startup rather than mid-run.
Results are cached in a module-level dict keyed by `cache_key(name, style_id)` —
`"continue"` for shared prompts, `"business_meeting/chunk"` for style prompts.
`reload_prompts()` clears and reloads, which is what File → Reload System
Prompts calls.

`prompts_dir()` resolves the prompt root across three environments: the package
directory in development, PyInstaller's `_MEIPASS` in a frozen bundle, and the
installed package location.

### There are no template placeholders

Prompts are static UTF-8 text loaded verbatim. Nothing is substituted into them.
Dynamic content is wrapped by the summarizer in code using fixed Markdown
headings: `## Transcript segment`, `## Already recorded, background only`,
`## Draft summary`, `## Section extracts`, `### Section N`, `### Extract N`, and
`## Sections turned off by the user`.

Angle-bracket text inside prompt files, such as
`## <Topic as the speakers framed it>`, is an instruction to the model, not a
placeholder. `tests/test_prompt_content.py` enforces this by failing on `{`,
`}`, `TODO`, `FIXME`, or `XXX` anywhere in a prompt file, and also asserts
per-file character ceilings so a prompt cannot grow large enough to crowd out
the transcript.

### Public API

```python
style_ids() -> tuple[str, ...]
is_known_style(style_id: str | None) -> bool
normalize_style(style_id: str | None) -> str        # unknown → DEFAULT_STYLE
get_style(style_id: str | None) -> SummaryStyle
style_display_name(style_id: str | None) -> str
style_sections(style_id: str | None = None) -> tuple[SummarySection, ...]
normalize_excluded_sections(style_id, excluded_ids) -> tuple[str, ...]
excluded_section_headings(style_id, excluded_ids) -> tuple[str, ...]
get_prompt(name: str, style_id: str | None = None) -> str
load_prompts() -> dict[str, str]
reload_prompts() -> dict[str, str]
```

## The twelve styles

`DEFAULT_STYLE` is `meeting_summary`.

| Style ID | Display name | Pipeline | What it produces |
|---|---|---|---|
| `pure_transcription` | Pure Transcription | sequential | A cleaned transcript with `**Speaker:**` turns, no summarising |
| `meeting_summary` | Meeting Summary | meeting | Overview plus full detailed notes |
| `pitch_deck` | Pitch Deck | document | Slide-ready outline: problem, solution, proof, ask |
| `internal_newsletter` | Internal Newsletter | document | Candid team update |
| `external_newsletter` | External Newsletter | document | Customer-safe update with internal material stripped |
| `technical_meeting` | Technical Meeting | document | Decision record: context, options, decision, consequences |
| `art_meeting` | Art Meeting | meeting | Visual direction, references, asset approvals |
| `design_meeting` | Design Meeting | meeting | Problem framing, constraints, alternatives, prototype next |
| `business_meeting` | Business Meeting | meeting | Goals, numbers, stakeholders, commercial decisions |
| `casual_meeting` | Casual Meeting | meeting | The same facts in a warmer recap voice |
| `standup_meeting` | Stand-Up Meeting | document | Per-person updates plus team themes |
| `ai_voiced_dialogue` | AI Voiced Dialogue | sequential | Two-host recap script for text-to-speech |

`technical_meeting` is the only style with a non-empty `required_sections`
(`("decision",)`), meaning a merge output lacking the word "decision" is treated
as truncated and continued. The five `meeting` styles require
`("action items", "open questions")` and place `Closing Assessment` last.

## Sections

A style declares which of its sections the user may switch off. Sections that
are structurally essential are simply not registered, so they cannot be removed.

```python
@dataclass
class SummarySection:
    section_id: str
    label: str                    # checkbox text in the dialog
    description: str
    headings: tuple[str, ...]     # the ## headings this section owns
    default_included: bool = True
```

| Style | Toggleable sections |
|---|---|
| `meeting_summary`, `casual_meeting` | executive_summary, decisions, action_items, open_questions, risks, detailed_notes, closing_assessment |
| `art_meeting` | the above plus visual_direction, references, assets, feedback_approvals |
| `design_meeting` | the above plus problem_framing, constraints, alternatives, prototype_next |
| `business_meeting` | the above plus goals_kpis, numbers_budget, stakeholders, timeline |
| `technical_meeting` | context, options, consequences, open_questions, technical_details, follow_ups |
| `pitch_deck` | insight, proof, market, business_model, ask, risks_objections |
| `internal_newsletter` | short_version, decisions, owners, still_open, whats_next, shoutouts |
| `external_newsletter` | in_this_issue, whats_shipping, whats_next, thank_you |
| `standup_meeting` | team_themes, blockers, announcements, shoutouts |
| `pure_transcription`, `ai_voiced_dialogue` | none |

Exclusion is enforced three times over, deliberately:

1. `_exclusion_directive()` appends `## Sections turned off by the user` to the
   merge, validate, and format prompts, so the model does not write them.
2. `strip_excluded_sections()` in `section_filter.py` removes any matching `##`
   section (and its `###` subsections) from the output anyway.
3. `detailed_notes` is special. Its ID is `SEGMENT_NOTES_SECTION_ID`, and
   excluding it skips `assemble_notes()` entirely rather than stripping headings
   afterwards.

Excluding sections also shrinks the `required_sections` list used by the
truncation check, so turning off "Action Items" does not make every merge look
truncated.

The user's choices persist per style in
`AppSettings.summary_excluded_sections`, a dict keyed by style ID, validated on
load against the current registry so a renamed section cannot corrupt settings.
`SummarySectionsDialog` is skipped entirely for styles with no toggleable
sections.

## Ollama integration

The client is `ollama.Client()` with default host and no configured timeout.
Everything is streamed; there is no non-streaming path.

```python
client.generate(
    model=..., system=..., prompt=..., stream=True, think=False,
    options={"num_predict": ..., "num_ctx": ..., "temperature": 0.2},
)
```

`think=False` suppresses reasoning output on models that support it. If the
installed `ollama` package predates that keyword, the call is retried without
it. When a model emits reasoning tokens anyway, they are surfaced separately
through an `on_reasoning` callback so the UI can show activity, and are used as
the response only if the response channel came back empty.

The default model is `RequirementsSummarizer.MODEL_NAME = "qwen3.5:9b"`, which
is also the `AppSettings.ollama_model` default.

Context length is the user's choice, from
`OLLAMA_CTX_CHOICES = (4096, 8192, 16384, 32768, 65536, 131072)`, defaulting to
8192. The model's own maximum context is read via `client.show()` and
`extract_context_length()` for display only — every budget derives from the
user's slider, not from the model's ceiling.

### Out-of-memory handling

`is_out_of_memory_error()` pattern-matches the exception and raises
`OllamaOutOfMemoryError`, which propagates up to the worker rather than being
retried in place. See [Architecture](architecture.md#degradation-and-recovery)
for why notes OOM is interactive while transcription OOM is automatic.

The recovery choices are:

| Choice | Effect | Can be saved as a policy |
|---|---|---|
| `REDUCE_CTX` | Drop to `previous_ollama_num_ctx(current)` and retry | yes |
| `SMALLER_MODEL` | Switch to the largest installed model smaller than the current one | yes |
| `RETRY` | Retry unchanged | no |
| `STOP` | Stop, keep what was already written | no |

Saved policies live in `AppSettings.ollama_oom_policy`, one of `""`,
`"reduce_ctx"`, or `"smaller_model"`. The dialog reappears whenever the saved
policy cannot be applied — for example when the context is already at the
minimum, or when no smaller model is installed.

## Model catalogs

`AddModelsDialog` browses and downloads models through a common
`CatalogProvider` protocol in `models/model_catalog.py`. There are four
providers:

| Provider | ID | Title in the dialog | Source |
|---|---|---|---|
| `WhisperCatalogProvider` | `whisper` | Transcribe audio | Hugging Face, Systran repos |
| `AlignmentCatalogProvider` | `alignment` | Align word timestamps | Hugging Face |
| `DiarizationCatalogProvider` | `diarization` | Detect speakers | Hugging Face, pyannote |
| `OllamaCatalogProvider` | `ollama` | Write meeting notes | ollama.com, then the `ollama` CLI, then a pinned list |

Whisper's short names map to Systran CTranslate2 repositories through
`WHISPER_SHORT_TO_REPO`, so `large-v3` resolves to
`Systran/faster-whisper-large-v3`.

The Ollama provider degrades through three discovery methods because
ollama.com has no stable public API: it scrapes the search page, falls back to
the CLI, and finally falls back to two pinned families (`llama3.2` and
`qwen2.5`) so the dialog is never empty.

Downloads run on `CatalogDownloadWorker` with aggregated progress. Models the
user adds are remembered in `extra_whisper_models`, `extra_alignment_models`,
and `extra_diarization_models` so they stay in the combo boxes.
