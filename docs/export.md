# Export subsystem

Two distinct things are exported, and they take different paths.

**Transcript exports** turn a `TranscriptResult` into a text file. Six formats,
one function each, all synchronous.

**PDF meeting notes** turn generated notes Markdown into a typeset document.
This runs on a worker thread, may invoke the language model first, and goes
through a four-module subsystem with two interchangeable rendering engines.

## Transcript formats

`speaker_transcriber/export/__init__.py` holds the registry:

```14:21:speaker_transcriber/export/__init__.py
EXPORTERS: dict[str, tuple[str, Callable[[TranscriptResult, Path], None]]] = {
    "txt": (".txt", export_text),
    "md": (".md", export_markdown),
    "json": (".json", export_json),
    "srt": (".srt", export_srt),
    "vtt": (".vtt", export_vtt),
    "csv": (".csv", export_csv),
}
```

`export_result(result, output_directory, formats)` creates the directory, names
each file after the stem of the first source file, and returns the paths it
wrote. Unknown format keys raise `ValueError`.

Every exporter is split into a `render_*` function returning a string and an
`export_*` function that writes it. Tests exercise the render functions, so
format assertions never touch the filesystem.

PDF is deliberately absent from this registry. It consumes a parsed
`MeetingDocument`, not a `TranscriptResult`, and has a different entry point.

### TXT

Blank-line-separated blocks:

```
[00:00:02 - 00:00:06] Alice
Welcome everyone.
```

Timestamps are `HH:MM:SS` with no milliseconds. When a block has
`overlapping_speakers`, the header gains ` overlap: Bob, Carol` using display
names.

`text_exporter.py` also provides `render_summary_source()`, which prepends a
speaker legend. That is the form fed to the language model, not to the user —
the legend tells the model which labels are real names and which are still
generic.

### Markdown

```markdown
# Transcript: recording.mp4

## Alice
*00:00:02 – 00:00:06*

Welcome everyone.

> Overlapping speech: Bob
```

An en dash separates the timestamps; the overlap line appears only when needed.

### JSON

The lossless format, and the one the transcript cache stores. Written with
`indent=2, ensure_ascii=False`.

| Field | Type | Always present |
|---|---|---|
| `source_file` | string | yes |
| `source_files` | string[] | only when set |
| `language` | string | yes |
| `duration_seconds` | number | yes |
| `speakers` | `{id: display_name}` | yes |
| `metadata.speaker_display_names` | `{id: display_name}` | yes |
| `segments` | array | yes |
| `alignment_available` | boolean | yes |
| `diarization_available` | boolean | yes |
| `fallback_config` | object | only when non-empty |

Each segment carries `start`, `end`, `speaker` (the raw ID, not the display
name), `text`, and `words`; plus `overlapping_speakers` and `uncertain` only
when meaningful. Each word carries `word`, `start`, `end`, `speaker`, and the
same two optional fields.

`from_json_dict()` reads it back, merging `metadata.speaker_display_names` into
`speakers` and supplying defaults for anything missing. This round trip is what
makes the transcript cache work.

### CSV

Exactly four columns: `start`, `end`, `speaker`, `text`. Times are formatted to
three decimal places; the speaker is the display name.

```
start,end,speaker,text
2.100,6.400,Speaker 1,Welcome.
```

### SRT and WebVTT

SRT numbers its cues from 1, uses a comma before milliseconds, and prefixes the
text with `Speaker: `.

WebVTT opens with a `WEBVTT` line, uses a period before milliseconds, and
carries the speaker in a voice tag: `<v Alice>Welcome everyone.`

### Shared helpers

`export/common.py` holds what the formats have in common:

| Function | Behaviour |
|---|---|
| `clock_timestamp(seconds, milliseconds=False)` | `HH:MM:SS` or `HH:MM:SS.mmm`; negatives clamp to zero |
| `subtitle_timestamp(seconds, separator=",")` | The above with milliseconds, separator swapped |
| `display_speaker(result, speaker)` | Display name, falling back to the raw ID |
| `speaker_color_map(result)` | Sorted speaker IDs cycled through `SPEAKER_COLORS` |
| `speaker_speaking_seconds(result)` | Total speaking time per speaker |
| `format_speaking_duration(seconds)` | `"45.3 s"`, `"2m 15s (135.0 s)"`, `"1h 2m 3s (…)"` |
| `render_speaker_legend(result)` | The legend prepended to model input |

`SPEAKER_COLORS` is the eight-colour palette used to tint speakers in the
transcript view and the speaker table: `#4FC3F7`, `#FFB74D`, `#81C784`,
`#BA68C8`, `#E57373`, `#4DB6AC`, `#FFD54F`, `#90A4AE`.

There is no filename sanitisation. Output names come from the source file stem
as-is.

## The PDF subsystem

```
notes Markdown
      │
      ▼  parse_meeting_markdown()
MeetingDocument                 ← structured model, engine-independent
      │
      ▼  export_meeting_pdf(document, path, engine, theme, style, options)
      │
      ├── layout_for(style)  →  apply_pdf_options(layout, options)   shape
      └── palette_for(theme, style)                                  colour
      │
      ├── ReportLab renderer   (default; pure Python)
      └── WeasyPrint renderer  (HTML/CSS; needs GTK libraries)
```

Four modules divide the work:

| Module | Owns |
|---|---|
| `pdf_layout.py` | The *shape* of the document per style: front matter, orientation, table of contents, speaker turns, footer label |
| `pdf_theme.py` | The *colour* of the document: seven palettes plus per-style accent tinting |
| `pdf_options.py` | User toggles that modify the layout |
| `pdf_exporter.py` | The ReportLab renderer, and the dispatcher both engines go through |
| `weasyprint_exporter.py` | The HTML/CSS renderer |
| `meeting_document.py` | Parsing Markdown into the document model |
| `participants.py` | Finding participant names in prose and colouring them |

Splitting layout from theme is what lets a user pick "Sepia" for a pitch deck
and get a warm cream landscape slide deck rather than a fixed pairing. Both
renderers read the same two objects, so the engine choice does not change the
document.

### Engine selection and fallback

`export_meeting_pdf(document, path, engine="reportlab", theme="light", style=None, options=None)`
defaults to ReportLab and falls back to the other engine if the requested one is
unavailable, logging a warning. Only when both are missing does it raise, with a
message naming both install options.

ReportLab is the default because it is pure Python and always present.
WeasyPrint produces better typography but needs GTK/Pango native libraries; on
Windows `configure_weasyprint_libraries()` searches MSYS2 and GTK install paths
for `libgobject-2.0-0.dll` and populates `WEASYPRINT_DLL_DIRECTORIES` before the
import is attempted.

### Layouts

`PdfLayout` is a frozen dataclass with four front-matter kinds: `COVER` (a
dedicated first page then a page break), `MASTHEAD` (a banner with body flowing
underneath), `COMPACT` (a small header band, no break), and `PLAIN` (a running
title only).

| Style | Kind | Kicker | Front matter | Notable |
|---|---|---|---|---|
| `meeting_summary` | meeting_cover | Meeting notes | COVER | TOC, participants |
| `art_meeting` | meeting_cover | Art review | COVER | TOC, participants |
| `design_meeting` | meeting_cover | Design review | COVER | TOC, participants |
| `business_meeting` | meeting_cover | Business review | COVER | TOC, participants |
| `casual_meeting` | meeting_cover | Team catch-up | COVER | TOC, participants |
| `technical_meeting` | adr_cover | Decision record | COVER | Fallback title "Technical Decision Record" |
| `pitch_deck` | pitch_slides | Pitch | COVER | Landscape, one slide per section, no TOC, footer "Slide" |
| `internal_newsletter` | newsletter | Team update | MASTHEAD | No TOC, no participants |
| `external_newsletter` | newsletter | Customer update | MASTHEAD | No TOC, no participants |
| `standup_meeting` | standup | Stand-up | COMPACT | Person cards |
| `pure_transcription` | transcript | Transcript | PLAIN | Speaker turns |
| `ai_voiced_dialogue` | dialogue | Voiced dialogue | COMPACT | Speaker turns |

Unknown style IDs normalise to the default layout.

### Options

`pdf_options.py` is a small registry designed to grow. Currently one option is
registered:

| Option ID | Label | Default | Applies to |
|---|---|---|---|
| `cover_page` | Large cover page | `True` | Styles whose front matter is `COVER` |

Turning it off rewrites the layout's front matter from `COVER` to `COMPACT`,
which is why the effect is described on the layout rather than checked during
rendering.

`PdfOption.needs_front_matter` drives dialog filtering, so the checkbox does not
appear for newsletters or transcripts where it would do nothing.

Only deviations from defaults are persisted. `pdf_option_deviations()` strips
anything matching its default before the value reaches `AppSettings.pdf_options`,
so adding a new option with a sensible default does not require a settings
migration.

`PdfExportChoices.build(theme, options)` normalises a theme ID and fills in
option defaults, and is what the dialog returns.

### Themes

Seven themes, registered in `PDF_THEME_CHOICES`, default `light`:

| Theme ID | Label | Mode | Style tinting | Intent |
|---|---|---|---|---|
| `light` | Light | light | yes | Crisp white page; safest for printing and sharing |
| `dark` | Dark | dark | yes | Charcoal page matching the app, for reading on screen |
| `sepia` | Sepia | light | yes | Warm cream paper and soft brown ink for long reads |
| `slate` | Slate | light | yes | Cool blue-grey report paper |
| `midnight` | Midnight | dark | yes | Deep navy with bright accents, for presenting |
| `contrast` | High contrast | light | **no** | Pure black on white, maximum legibility |
| `mono` | Grayscale | light | **no** | No colour, for monochrome printers and photocopiers |

`contrast` and `mono` set `tint_with_style=False`, because tinting them with a
style accent would defeat their entire purpose. For the other five,
`palette_for(theme, style)` overrides `accent`, `accent_soft`, `heading`,
`rule_strong`, and `table_header_background` with the style's accent — chosen by
the theme's *mode*, not its ID, so a new dark theme automatically gets the dark
accent variants.

Full hex values for every palette and every style accent are in the
[design system](design-system.md#pdf-palettes).

### The document model

`meeting_document.py` parses generated Markdown into a structure both renderers
can walk. This exists because rendering Markdown twice, once per engine, would
guarantee the two engines diverge.

`MeetingDocument` holds a `title`, `subtitle`, `participants`, `primary_topics`,
and a list of `Section`. Each section has a title and a list of blocks:
`ParagraphBlock`, `HeadingBlock`, `NumberedListBlock`, `BulletListBlock`,
`ActionTableBlock` (rows of `ActionItem` with owner, action, priority), and
`RiskListBlock` (`RiskItem` with text and mitigation).

`parse_meeting_markdown()` unwraps a stray fenced code block if the model
wrapped its whole answer in one, extracts the title and subtitle, reads
`Participants:` and `Primary topics:` metadata tolerantly (bold or plain,
possibly wrapped over lines), splits on major headings, and parses blocks within
each section. Risk sections get special treatment, pairing each risk with a
following `Mitigation:` line.

Supporting utilities:

| Function | Purpose |
|---|---|
| `is_usable_summary_markdown(text)` | Rejects empty text, "generating summary", "summary failed", and placeholders |
| `strip_inline_markdown(text)` | Removes bold, italic, inline code |
| `split_turn(text)` | Parses `**Speaker:** text` dialogue lines |
| `as_script(document)` | Moves spoken title and subtitle into the body for transcript and dialogue layouts |
| `needs_format_pass(...)` | True when the document lacks a title, named sections, or an action table — triggers the formatting LLM pass |

### Participants

`participants.py` finds people's names in prose and colours them, which is what
makes a generated document scannable.

`parse_participants(raw)` splits on commas, semicolons, slashes, ampersands, and
the word "and"; strips punctuation; drops generic placeholders like "everyone",
"team", "others", and "unknown"; and deduplicates on a normalised alphanumeric
key of at least three characters.

`build_highlighter()` produces a `ParticipantHighlighter` that assigns each name
a colour from the palette's `participants` tuple, cycling when there are more
people than colours. Matching is fuzzy — `SequenceMatcher` with a 0.86 minimum
ratio and a same-first-letter requirement — over capitalised words and two-word
phrases, so "Alex" matches "Alexander" but not "Alexa". HTML tags and entities
are skipped so the WeasyPrint path cannot be corrupted by a name that looks like
markup.

Script layouts (transcript, dialogue) use a separate mechanism, assigning
speaker colours by first appearance rather than by participant matching.

### Typography

Both engines target the same sizes so the two outputs are comparable.

| | ReportLab | WeasyPrint |
|---|---|---|
| Body | Helvetica 10.5 pt, leading 16, justified | `"Segoe UI", Helvetica, Arial, sans-serif` 10.5 pt, line-height 1.5 |
| Bold / italic / code | Helvetica-Bold / Helvetica-Oblique / Courier | font-weight and font-style |
| Page | US Letter, landscape for `pitch_deck` | `@page` with matching margins |
| Margins | 0.9 in sides, 1.0 in top, 0.85 in bottom | `1in 0.9in 0.85in 0.9in` |
| Cover title | 30 pt (34 pt for slides) | same |
| H1 / H2 / H3 | 21 / 14 / 11.5 pt (H2 26 pt for slides) | same |
| Speaker turns | 54 pt hanging indent | equivalent indent |

A table of contents is rendered when the document has at least two named
sections. Anchors are slugified as `sec-{slug}` with deduplication.
