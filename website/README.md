# Summit marketing website

The public site for Summit, the local speaker-transcription desktop app in the
parent repository. Next.js 16 (App Router), TypeScript, Tailwind CSS 4, and
Motion for animation.

The colour tokens, typography, and logo mark are ported from the desktop
application so the two look like the same product. If you change
`speaker_transcriber/ui/theme.py`, mirror it in `app/globals.css`.

## Running it

Use the management scripts in the repository's `scripts/` directory. They work
from any directory, install dependencies on first use, and track the background
server so it can be stopped again.

```powershell
# Windows — listens on 0.0.0.0:3100 so phones and tablets on the LAN can open it
.\scripts\website.ps1 start
.\scripts\website.ps1 status
.\scripts\website.ps1 stop
```

```bash
# Linux and macOS
./scripts/website.sh start
./scripts/website.sh status
./scripts/website.sh stop
```

Full command list: `install`, `dev`, `serve`, `build`, `start`, `stop`,
`restart`, `status`, `logs`, `open`, `lint`, `check`, `clean`, `reset`.

Or drive npm directly from this directory:

```bash
npm install
npm run dev
npm run build
npm run start
npm run lint
```

## Configuration

Copy `.env.example` to `.env.local`. Every value is optional and the site
degrades gracefully without them.

| Variable | Effect when unset |
|---|---|
| `NEXT_PUBLIC_DOWNLOAD_URL` | Trial buttons point at `/download`. |
| `NEXT_PUBLIC_WINDOWS_INSTALLER_URL` | `/download` shows the "being packaged" panel and a launch-list form instead of a download button. |
| `NEXT_PUBLIC_WAITLIST_URL` | The launch-list form confirms locally without posting anywhere. |

The waitlist form POSTs `{ "email": "..." }` as JSON, which suits Formspree,
Getform, Basin, and most similar endpoints.

## Where the content lives

Copy is data, not markup. Edit these rather than hunting through components:

- `lib/content.ts` — features, pipeline stages, notes styles, audiences, FAQ,
  privacy points
- `lib/pricing.ts` — plans and prices. The paid tiers are placeholders.
- `lib/site.ts` — product name, tagline, trial length, navigation links

The notes-style list mirrors `SUMMARY_STYLES` in
`speaker_transcriber/prompts/__init__.py`. Keep them in sync when a style is
added or renamed.

## Structure

```
app/
  page.tsx          Landing page, one section per component
  download/         Trial download and setup checklist
  privacy/          What touches the network, in detail
  globals.css       Theme tokens ported from the desktop app
components/
  summit-mark.tsx   SVG port of paint_summit_mark() from branding.py
  app-preview.tsx   Animated mock of the desktop window
  reveal.tsx        Scroll-reveal wrapper, honours prefers-reduced-motion
lib/                Content, pricing, and site constants
```

## Accessibility and motion

Every animation is disabled or reduced when the operating system requests
reduced motion, through both a CSS media query in `globals.css` and Motion's
`useReducedMotion`. Scroll-revealed content is forced visible by a `<noscript>`
rule so the page still reads without JavaScript.
