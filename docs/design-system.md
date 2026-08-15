# Design system

The product has one visual language expressed in three places: the desktop
application (Qt stylesheet), exported PDF documents (ReportLab and WeasyPrint),
and the marketing website (Tailwind CSS). The application palette is the
original; the website tokens are a direct port of it, and the PDF `dark` theme
matches it as well.

Values below were read from source. When you change one, check whether its
counterparts need to change too — the three sets are kept in sync by hand, not
by tooling.

| Where | Source of truth |
|---|---|
| Desktop app | `speaker_transcriber/ui/theme.py` |
| Brand mark and fonts | `speaker_transcriber/ui/branding.py` |
| PDF documents | `speaker_transcriber/export/pdf_theme.py` |
| Website | `website/app/globals.css` |

## Principles

**Dark by default, everywhere on screen.** The app has no light mode and no
toggle; `window_chrome.py` forces `Qt.ColorScheme.Dark` and the website sets
`color-scheme: dark` at the root. Documents are the exception, because they get
printed — the PDF default is `light`.

**One accent, used sparingly.** `#7EC8D4`, a desaturated cyan, marks the primary
action, the current search match, focus rings, and the logo. Nothing else
competes with it.

**Speakers get colour; the interface does not.** The eight-colour speaker
palette is the only place where varied hue appears in the app, because
distinguishing speakers is the one thing colour genuinely has to do here.

**Documents follow the notes style.** A PDF's accent is tinted by the summary
style, so a design review reads purple and a business review reads navy, while
the reader's chosen theme still controls the page and text colours.

## Application palette

From `Theme` in `speaker_transcriber/ui/theme.py`:

| Token | Value | Used for |
|---|---|---|
| `WINDOW` | `#12181C` | Window background |
| `SURFACE` | `#1B2429` | Panels, group boxes, buttons |
| `SURFACE_RAISED` | `#232D33` | Elevated surfaces |
| `SURFACE_SUNKEN` | `#0E1316` | Text inputs, editors |
| `BORDER` | `#2E3A41` | Panel and control borders |
| `BORDER_SUBTLE` | `rgba(255, 255, 255, 0.09)` | Hairlines |
| `TEXT` | `#F4F7F8` | Primary text |
| `TEXT_MUTED` | `#9AA7AE` | Secondary text, placeholders |
| `TEXT_DIM` | `#B7C2C8` | Tertiary text |
| `ACCENT` | `#7EC8D4` | Primary action, selection, focus |
| `ACCENT_HOVER` | `#95D5DF` | Accent hover |
| `ACCENT_PRESSED` | `#5FA8B4` | Accent pressed, visited links |
| `ACCENT_SOFT` | `rgba(126, 200, 212, 0.18)` | Active-state backgrounds |
| `DANGER` | `#E57373` | Errors |
| `SUCCESS` | `#81C784` | Success |
| `SCROLLBAR` | `#3A474E` | Scrollbar thumb |
| `HIGHLIGHT_TEXT` | `#0E1316` | Text on accent backgrounds |

Values used in the stylesheet but not exposed as tokens:

| Purpose | Value |
|---|---|
| Button hover background | `#2B373E` |
| Button pressed background | `#1A2328` |
| Notification, info background | `#1E2C31` |
| Notification, success background | `#1C2A22` |
| Notification, warning border | `#FFB74D` |
| Notification, warning background | `#2A2418` |
| Notification, error background | `#2A1C1C` |
| Search match background | `#C9A44A` |
| Current search match background | `ACCENT` |

### Speaker colours

Eight colours cycled by speaker order, defined once in
`speaker_transcriber/export/common.py` as `SPEAKER_COLORS` and shared by the
transcript view, the speaker table, and the transcript heatmap:

`#4FC3F7` · `#FFB74D` · `#81C784` · `#BA68C8` · `#E57373` · `#4DB6AC` ·
`#FFD54F` · `#90A4AE`

The input timeline uses a near-identical set with `#7EC8D4` in the first slot
and `#CE93D8` in place of `#BA68C8`, since it is colouring source files rather
than speakers.

## Typography

**Interface** — `Segoe UI Variable`, `Segoe UI`, `Inter`, `Arial`, at 10 pt.
The fallback chain covers Windows 11, Windows 10, systems with Inter installed,
and everything else.

**Display** — Space Grotesk Bold, bundled at
`speaker_transcriber/assets/fonts/SpaceGrotesk-Bold.ttf`, falling back to
`Bahnschrift`, `Segoe UI Variable Display`, `Segoe UI`, `Arial`. Used for the
wordmark at 24 pt with 2.6 px letter-spacing, and on the splash at 28 pt in
small caps.

Sizes set in the stylesheet:

| Element | Size | Weight |
|---|---|---|
| Stage label and percentage | 12 px | 600 on the percentage |
| Model field captions | 11 px | normal |
| Resource meter captions | 10 px | normal |
| Notification text | 12 px | 600 |
| Group box titles, table headers, primary buttons, collapse toggles | inherited | 600 |
| Summary text editor | 12 pt | normal |

## Spacing and shape

| Context | Value |
|---|---|
| Window root margins | 10, 8, 10, 8 |
| Window root spacing | 6 |
| Setup section content | margins 10, 0, 10, 8; spacing 6 |
| Collapsible section content | margins 12, 4, 12, 12 |
| Status strip | margins 8, 6, 8, 6 |
| Group box | margin-top 14 px, padding 14/12/12/12 |
| Button | padding 7 × 14 px, min-height 18 px |
| Input | padding 6 × 8 px |
| Tab | padding 8 × 16 px, margin-right 4 px |
| Menu item | padding 7px 18px 7px 32px |
| Notification banner | margins 18, 10, 18, 10 |

Radii: 10 px for large containers (group boxes, tab panes, collapsible sections,
notification banners), 8 px for controls (buttons, inputs, tables, menus, tab
tops), 6 px for tooltips and the status strip, 4 px for checkbox and menu
indicators and meter bars, and 16 px for the splash card.

## The Summit mark

`paint_summit_mark()` in `speaker_transcriber/ui/branding.py` draws the logo
programmatically at every size it is needed (16, 20, 24, 32, 40, 48, 64, 128,
256 px), so it stays sharp without a set of raster assets. A pre-rendered
`assets/summit.ico` is used for the executable icon when present.

The mark is a mountain silhouette with voice waves and a beacon at the summit:

| Element | Colours |
|---|---|
| Tile frame gradient | `#2A3940` → `#1B2429` → `#12181C` |
| Accent glow | `rgba(126, 200, 212, 70)` → transparent |
| Rim | `rgba(126, 200, 212, 48)` |
| Mountain fill | `#D7F4F8` → `#7EC8D4` → `#5FA8B4` |
| Voice waves | `#95D5DF`, fading by index |
| Beacon core | `#F4F7F8` |

`website/components/summit-mark.tsx` is an SVG port of the same drawing, using
the same colours.

## PDF palettes

Each theme defines fourteen colour roles. The values below are the **base**
palettes as written in `pdf_theme.py`. For the five themes with
`tint_with_style = True`, five of those roles are replaced at render time by the
summary style's accent — see [style tinting](#style-tinting) below.

### light — default; crisp white page, safest for printing

| Role | Value |
|---|---|
| page | `#FFFFFF` |
| text | `#1B2429` |
| muted | `#5C6B73` |
| accent | `#1F7A8C` |
| accent_soft | `#E3F0F3` |
| heading | `#12303A` |
| rule | `#D3DDE1` |
| rule_strong | `#1F7A8C` |
| surface | `#F4F8F9` |
| surface_alt | `#EDF3F5` |
| table_header_background | `#1F7A8C` |
| table_header_text | `#FFFFFF` |
| border | `#C6D3D8` |
| participants | `#1F6FB2` `#B25E00` `#2E7D32` `#7B3FA0` `#C0392B` `#8D6E00` `#0E7C6B` `#4E6472` |

### dark — charcoal page matching the application

| Role | Value |
|---|---|
| page | `#12181C` |
| text | `#F4F7F8` |
| muted | `#9AA7AE` |
| accent | `#7EC8D4` |
| accent_soft | `#1F3239` |
| heading | `#7EC8D4` |
| rule | `#2E3A41` |
| rule_strong | `#7EC8D4` |
| surface | `#1B2429` |
| surface_alt | `#232D33` |
| table_header_background | `#245560` |
| table_header_text | `#F4F7F8` |
| border | `#2E3A41` |
| participants | `#9CC9F0` `#FFB86B` `#8FD48F` `#C89BE8` `#F29191` `#F5D77E` `#63C9B4` `#B7C3CA` |

### sepia — warm cream paper for long reads

| Role | Value |
|---|---|
| page | `#FBF3E4` |
| text | `#3B2F22` |
| muted | `#7A6A55` |
| accent | `#A0642B` |
| accent_soft | `#F1E3CC` |
| heading | `#4A3520` |
| rule | `#E0D2B8` |
| rule_strong | `#A0642B` |
| surface | `#F5EAD6` |
| surface_alt | `#EFE2CA` |
| table_header_background | `#7A5327` |
| table_header_text | `#FBF3E4` |
| border | `#DCCBAC` |
| participants | `#1D5FA8` `#A9500F` `#2F6B34` `#7A3E96` `#B03A2E` `#7A5B00` `#0F6E60` `#5A4A3A` |

### slate — cool blue-grey report paper

| Role | Value |
|---|---|
| page | `#EEF2F6` |
| text | `#1E2933` |
| muted | `#5A6B7B` |
| accent | `#2E6E9E` |
| accent_soft | `#DCE7F0` |
| heading | `#16242F` |
| rule | `#C8D4DE` |
| rule_strong | `#2E6E9E` |
| surface | `#E3EAF1` |
| surface_alt | `#DAE3EB` |
| table_header_background | `#2E6E9E` |
| table_header_text | `#FFFFFF` |
| border | `#BCCAD6` |
| participants | `#17568C` `#96540A` `#256B2A` `#66358A` `#A6332A` `#77600B` `#0B6558` `#3A4B5C` |

### midnight — deep navy for presenting on screen

| Role | Value |
|---|---|
| page | `#0E1428` |
| text | `#E9EDF7` |
| muted | `#97A2C0` |
| accent | `#7FA8FF` |
| accent_soft | `#1B2445` |
| heading | `#9DC0FF` |
| rule | `#26304F` |
| rule_strong | `#7FA8FF` |
| surface | `#161E38` |
| surface_alt | `#1D2745` |
| table_header_background | `#2A3766` |
| table_header_text | `#E9EDF7` |
| border | `#26304F` |
| participants | `#8FB6FF` `#FFC08A` `#93E0A8` `#D3A8F5` `#FF9C9C` `#F2DA8C` `#6FD8C6` `#B9C4DE` |

### contrast — pure black on white, no style tinting

| Role | Value |
|---|---|
| page | `#FFFFFF` |
| text | `#000000` |
| muted | `#333333` |
| accent | `#000000` |
| accent_soft | `#E6E6E6` |
| heading | `#000000` |
| rule | `#000000` |
| rule_strong | `#000000` |
| surface | `#F0F0F0` |
| surface_alt | `#E4E4E4` |
| table_header_background | `#000000` |
| table_header_text | `#FFFFFF` |
| border | `#000000` |
| participants | `#0033A0` `#8A3B00` `#00591F` `#5B0091` `#9E0018` `#4A4A00` `#00504B` `#1A1A1A` |

### mono — grayscale for monochrome printing, no style tinting

| Role | Value |
|---|---|
| page | `#FFFFFF` |
| text | `#1A1A1A` |
| muted | `#595959` |
| accent | `#4D4D4D` |
| accent_soft | `#EDEDED` |
| heading | `#262626` |
| rule | `#C7C7C7` |
| rule_strong | `#4D4D4D` |
| surface | `#F4F4F4` |
| surface_alt | `#EAEAEA` |
| table_header_background | `#3D3D3D` |
| table_header_text | `#FFFFFF` |
| border | `#BFBFBF` |
| participants | `#1A1A1A` `#4D4D4D` `#757575` `#2E2E2E` `#616161` `#8A8A8A` `#3F3F3F` `#6B6B6B` |

### Style tinting

`palette_for(theme, style)` replaces `accent`, `accent_soft`, `heading`,
`rule_strong`, and `table_header_background` with the style's accent set, chosen
by the theme's **mode** rather than its ID. A new dark theme therefore inherits
the dark accents automatically.

`contrast` and `mono` opt out entirely, so they always render exactly as listed
above.

Because tinting is keyed on mode, `sepia` and `slate` — both light-mode — render
the *light* accent of the chosen style, not their own base accent. Their base
`accent` values only apply if a style has no registered accent.

| Style | Light: accent / soft / heading / table header | Dark: accent / soft / heading / table header |
|---|---|---|
| `meeting_summary` | `#1F7A8C` `#E3F0F3` `#12303A` `#1F7A8C` | `#7EC8D4` `#1F3239` `#7EC8D4` `#245560` |
| `art_meeting` | `#B4543A` `#F7E7E1` `#4A2018` `#B4543A` | `#F0A28B` `#38221C` `#F0A28B` `#6B3325` |
| `design_meeting` | `#6B4FA8` `#EDE7F8` `#2E2150` `#6B4FA8` | `#C4AEF0` `#2A2340` `#C4AEF0` `#46356F` |
| `business_meeting` | `#1F4E79` `#E3ECF5` `#10263B` `#1F4E79` | `#8FB8E0` `#1B2836` `#8FB8E0` `#24466B` |
| `casual_meeting` | `#4C7A50` `#E7F1E6` `#1F3A22` `#4C7A50` | `#9BCE9E` `#1F2C20` `#9BCE9E` `#35573A` |
| `technical_meeting` | `#46596B` `#E8ECF0` `#1E2A34` `#46596B` | `#A9BCCD` `#232C34` `#A9BCCD` `#3A4B5A` |
| `pitch_deck` | `#0E7C86` `#DFF1F2` `#062E33` `#0E7C86` | `#57D6DF` `#123033` `#57D6DF` `#12606A` |
| `internal_newsletter` | `#2A5DB0` `#E5ECF9` `#14294F` `#2A5DB0` | `#9DBDF2` `#1B2740` `#9DBDF2` `#2F4F86` |
| `external_newsletter` | `#A6791F` `#FAF1DC` `#33270A` `#A6791F` | `#E8C46A` `#33290F` `#E8C46A` `#6B5216` |
| `standup_meeting` | `#17868A` `#E1F1F1` `#0F3335` `#17868A` | `#6FD3D6` `#16302F` `#6FD3D6` `#1E5F62` |
| `pure_transcription` | `#4A5568` `#EDEFF2` `#1B2429` `#4A5568` | `#B3BDC8` `#232B33` `#B3BDC8` `#3B4653` |
| `ai_voiced_dialogue` | `#8E3D8A` `#F6E6F5` `#3A153A` `#8E3D8A` | `#E39BDF` `#2F2033` `#E39BDF` `#5E2A5C` |

## Website tokens

`website/app/globals.css` declares the design system in a Tailwind v4 `@theme`
block. There is no `tailwind.config.*`; the CSS is the config.

| Token | Value | App equivalent |
|---|---|---|
| `--color-window` | `#12181c` | `WINDOW` |
| `--color-surface` | `#1b2429` | `SURFACE` |
| `--color-raised` | `#232d33` | `SURFACE_RAISED` |
| `--color-sunken` | `#0e1316` | `SURFACE_SUNKEN` |
| `--color-edge` | `#2e3a41` | `BORDER` |
| `--color-ink` | `#f4f7f8` | `TEXT` |
| `--color-muted` | `#9aa7ae` | `TEXT_MUTED` |
| `--color-dim` | `#b7c2c8` | `TEXT_DIM` |
| `--color-accent` | `#7ec8d4` | `ACCENT` |
| `--color-accent-hover` | `#95d5df` | `ACCENT_HOVER` |
| `--color-accent-pressed` | `#5fa8b4` | `ACCENT_PRESSED` |
| `--color-danger` | `#e57373` | `DANGER` |
| `--color-success` | `#81c784` | `SUCCESS` |
| `--radius-panel` | `10px` | Large container radius |

Fonts come from `next/font/google`: Inter as `--font-inter` and Space Grotesk
(weights 500, 600, 700) as `--font-space-grotesk`, both with `display: swap`.
The theme composes them into `--font-sans` and `--font-display` with the same
fallback chains the app uses.

Four keyframe animations are registered as tokens:

| Token | Animation |
|---|---|
| `--animate-drift` | `drift 22s ease-in-out infinite` — background gradient blobs |
| `--animate-beacon` | `beacon 3.2s ease-in-out infinite` — the logo beacon pulse |
| `--animate-stripes` | `stripes 1.1s linear infinite` — the hazard progress bar in the app preview |
| `--animate-caret` | `caret 1.05s steps(2) infinite` — typing caret |

Two custom utilities carry app idioms onto the web: `panel` (1 px edge border,
panel radius, surface background) and `hazard-stripes` (a 115° repeating
gradient between the accent and pressed-accent colours, 28 px period) which
reproduces `HazardProgressBar`.

All animation is suppressed under `prefers-reduced-motion: reduce`, and a
`<noscript>` style forces revealed elements visible so the page reads without
JavaScript.
