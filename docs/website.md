# Marketing website

`website/` is a separate Next.js project for the public site. It is not needed
to build or run the desktop application, has no shared build, and no code
crosses between them — design values are copied by hand.

## Stack

| Package | Version |
|---|---|
| next | 16.3.0 (pinned) |
| react / react-dom | 19.2.8 (pinned) |
| motion | ^13.1.0 |
| tailwindcss | ^4 |
| @tailwindcss/postcss | ^4 |
| typescript | ^5 |
| eslint / eslint-config-next | ^9 / 16.3.0 |

App Router, TypeScript in strict mode, `@/*` aliased to the project root.
Tailwind v4 with no `tailwind.config.*` — the theme is declared in
`app/globals.css` via `@theme`, and PostCSS runs a single plugin,
`@tailwindcss/postcss`.

```json
"dev":   "next dev --hostname 0.0.0.0 --port 3100",
"build": "next build",
"start": "next start --hostname 0.0.0.0 --port 3100",
"lint":  "eslint"
```

Binding to `0.0.0.0:3100` rather than localhost is deliberate: it lets a phone
on the same network load the site for real-device testing.
`next.config.ts` sets `allowedDevOrigins: ["*"]` so HMR assets load from those
devices too.

There is no `output: 'export'`, so this is a Node.js deployment rather than a
static one. There is no image optimisation config and no use of `next/image` —
the site's only graphics are inline SVG and CSS.

## Routes

| Route | File | Content |
|---|---|---|
| `/` | `app/page.tsx` | Ten section components |
| `/download` | `app/download/page.tsx` | Animated logo, download CTA or waitlist, four setup steps |
| `/privacy` | `app/privacy/page.tsx` | Seven sections of policy prose, CTA to `/#waitlist` |

`app/layout.tsx` wraps everything in `SiteNav` and `SiteFooter`.

Homepage order: `Hero`, `PipelineStrip`, `Audiences`, `Features`, `NoteStyles`,
`PrivacySection`, `Pricing`, `Requirements`, `Faq`, `ClosingCta`.

Anchor targets used by the nav and footer: `#preview`, `#audiences`,
`#features`, `#notes`, `#privacy`, `#pricing`, `#requirements`, `#faq`,
`#waitlist`.

## Components

| Component | Purpose |
|---|---|
| `Hero` | Trial badge, headline, CTAs, platform badges, embedded `AppPreview`. Includes a decorative `BackdropMesh` of drifting gradient blobs |
| `AppPreview` | An animated mock of the desktop window — transcript, sidebar, notes panel, progress bar — on a 15-second loop simulating the pipeline |
| `PipelineStrip` | The five processing stages |
| `Audiences` | Two cards: businesses, and everyone else |
| `Features` | Eight feature cards plus export-format chips |
| `NoteStyles` | All twelve styles listed; four are clickable and swap a live Markdown preview |
| `PrivacySection` | Four privacy points, link to `/privacy` |
| `Pricing` | Four plan cards |
| `Requirements` | A requirements table and a VRAM bar chart |
| `Faq` | Accordion, first item open |
| `ClosingCta` | Final CTA with the waitlist form |
| `SiteNav` | Sticky header; gains a border after 12 px of scroll; hamburger menu on mobile |
| `SiteFooter` | Brand plus two link columns |
| `SummitMark` / `SummitWordmark` | SVG port of the desktop logo |
| `Reveal` | Scroll-reveal wrapper using Motion's `whileInView` |
| `SectionHeading` | Eyebrow, heading, optional body |
| `WaitlistForm` | Email capture |

`Reveal` and `SummitMark` are the only components with meaningful props:

```6:13:website/components/reveal.tsx
type RevealProps = {
  children: ReactNode;
  className?: string;
  delay?: number;
  /** Vertical travel in pixels; 0 fades in place. */
  distance?: number;
  as?: "div" | "section" | "li" | "article";
};
```

`SummitMark` takes `className`, `framed` (default true), `animated` (default
false), and `idPrefix` (default `"summit"`) — the prefix keeps SVG gradient IDs
unique when several marks share a page.

Both `Reveal` and the animated components call `useReducedMotion` and fall back
to fading in place, and `globals.css` clamps all animation to 0.001 ms under
`prefers-reduced-motion`.

## Content and data

Three files under `lib/` hold everything editable, so copy changes do not
require touching components.

**`lib/site.ts`** — product constants and configuration:

```1:25:website/lib/site.ts
export const SITE = {
  name: "Summit",
  tagline:
    "Locally generated, completely private transcription and summarization of multi-speaker meetings.",
  description:
    "Summit transcribes audio and video, labels every speaker, and writes meeting notes entirely on your own computer. Nothing is uploaded.",
  trialMinutes: 10,
} as const;

export const DOWNLOAD_URL =
  process.env.NEXT_PUBLIC_DOWNLOAD_URL ?? "/download";

export const WAITLIST_URL = process.env.NEXT_PUBLIC_WAITLIST_URL ?? "";

export const NAV_LINKS = [
  { href: "/#features", label: "Features" },
  { href: "/#notes", label: "Notes" },
  { href: "/#privacy", label: "Privacy" },
  { href: "/#pricing", label: "Pricing" },
] as const;
```

**`lib/pricing.ts`** — four plans. The amounts are marked as placeholders in a
source comment; changing `price` here updates the pricing section.

| Plan | Price | Cadence | CTA |
|---|---|---|---|
| Trial | Free | no card, no account | Download the trial → `/download` |
| Personal | $79 | one-time, one computer | Join the launch list → `/#waitlist` |
| Team | $249 | one-time, five computers | Join the launch list → `/#waitlist` |
| Business | Talk to us | volume and procurement | Start a conversation → `/#waitlist` |

Trial is the featured card. Its framing is that the only limit is recording
length — nothing is watermarked or withheld.

**`lib/content.ts`** — eight features, the five pipeline stages (Decode,
Transcribe, Align, Diarize, Write), all twelve note styles, two audience cards,
eight FAQ entries, and four privacy points.

These mirror application source. The note styles correspond to `SUMMARY_STYLES`
in `speaker_transcriber/prompts/__init__.py` and the pipeline stages to the
processor's stage table, so both need updating together.

## Waitlist form

`WaitlistForm` posts JSON `{ "email": … }` to `NEXT_PUBLIC_WAITLIST_URL` with
`Content-Type: application/json` and `Accept: application/json`. The URL is
expected to be a form-capture service such as Formspree, Getform, or Basin;
there is no API route in the project.

When the variable is unset, the form skips the network call and shows success
immediately, so the site works in development without configuration.

Validation is HTML5 only — `type="email"` and `required`. Duplicate submits are
ignored while a request is in flight. The four states are `idle`, `sending`
(button reads "Sending…", disabled, 60 % opacity), `done` (a green panel
reading "You are on the list."), and `error` (red text below the form).

### Environment variables

All optional; the site degrades gracefully without them.

| Variable | Effect |
|---|---|
| `NEXT_PUBLIC_WAITLIST_URL` | Form POST endpoint; unset means fake success |
| `NEXT_PUBLIC_DOWNLOAD_URL` | Download button target; defaults to `/download` |
| `NEXT_PUBLIC_WINDOWS_INSTALLER_URL` | Direct installer link on `/download`; when absent, that page shows the waitlist instead |

## Metadata

Root metadata sets the title `"Summit — private, local transcription with
speaker labels"` with the template `"%s — Summit"`, the shared description, and
Open Graph title, description, `siteName`, and `type`. The viewport sets
`themeColor: "#12181C"` — matching `--color-window`, so mobile browser chrome
blends with the page — and `viewportFit: "cover"` for notched displays, with
matching safe-area padding on the body.

There is no `og:image`, no `og:url`, and no Twitter card. Adding an OG image is
the obvious next step for link previews. The favicon is
`app/favicon.ico`, picked up by file convention.

Page-level metadata overrides the title on `/download` ("Download the free
trial") and `/privacy` ("Privacy").

## Running it

Wrapper scripts at the repository root manage the site, installing dependencies
on first use and tracking the background server by PID:

```powershell
.\scripts\website.ps1 start     # production server on 0.0.0.0:3100
.\scripts\website.ps1 serve     # background dev server
.\scripts\website.ps1 status
.\scripts\website.ps1 stop
```

```bash
./scripts/website.sh dev
./scripts/website.sh serve
./scripts/website.sh status
./scripts/website.sh stop
```

Other subcommands: `install`, `build`, `restart`, `logs`, `open`, `lint`,
`check`, `clean`, `reset`. Node.js 20 or newer is required.

The PowerShell script also offers to create a Windows firewall rule for the
port, which is what makes LAN testing work without manual configuration. That
rule applies to the website server only.
