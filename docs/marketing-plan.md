# Summit — Go-to-Market and Marketing Plan

**Product:** Summit (package name `speaker-transcriber`)
**Document owner:** Founder / product lead
**Version:** 1.0 — 13 August 2026
**Status:** Pre-launch. Marketing site exists; installer, licensing, and payment do not.

---

## 0. How to read this document

This plan covers positioning, pricing, channels, launch sequencing, and the
commercial blockers that have to close before any of it can run. Three
conventions are used throughout:

| Marker | Meaning |
|---|---|
| **Fact** | Verified in the repository today |
| **Recommendation** | A proposal that requires a decision |
| **Blocker** | Work that must complete before revenue is possible |

Numbers presented as market sizing are bottom-up estimates built from stated
assumptions, not vendor research figures. Every assumption is written down so it
can be argued with.

---

## 1. Executive summary

Summit is a Windows and Linux desktop application that transcribes audio and
video, labels who spoke, and writes finished meeting documents — entirely on the
user's own machine. Nothing is uploaded. There is no account, no server, and no
subprocessor.

The strategic opportunity is a genuine and unusual gap in the market. On macOS,
one-time-purchase local transcription is a solved, crowded category. On Windows
— which is where regulated industries, corporate laptops, and gaming-grade
NVIDIA GPUs actually live — the local options are either free-but-rough
open-source utilities or enterprise platforms sold through procurement. There is
no polished, purchasable, privacy-absolute desktop transcription product for
Windows with speaker diarization and document generation. Summit is that
product.

The plan rests on four decisions:

1. **Lead with privacy as an architectural fact, not a policy promise.** The
   competitive claim is not "we protect your data." It is "there is no server to
   protect it from." That claim is verifiable, and it is the only claim no cloud
   competitor can copy without rebuilding their business.

2. **Sell the finished document, not the transcript.** Twelve notes styles, PDF
   themes, and structured exports mean Summit replaces the hour of writing that
   follows a meeting, not just the typing. This moves the value conversation from
   cents-per-minute to hours-per-week.

3. **Run a consumer funnel to fund an enterprise motion.** The $79 personal
   license is a distribution and credibility engine. The revenue concentration is
   in regulated buyers — legal, healthcare, defence, government, journalism, HR
   investigations, clinical practice — who cannot use Otter.ai at all and are
   currently paying far more for far worse.

4. **Treat setup friction as the primary conversion risk.** Today a new user must
   install FFmpeg, verify an NVIDIA driver, create a Hugging Face account, accept
   two gated model licences, and optionally install Ollama before seeing a single
   word of output. That sequence will destroy a consumer funnel. Removing it is
   the highest-ROI marketing work available, and it is engineering work.

**Twelve-month target:** $180,000 in bookings — roughly 900 personal/team
licences (~$85,000) and 12–18 business agreements (~$95,000) — from a marketing
spend of $28,000.

---

## 2. What we are actually selling

### 2.1 The product in one paragraph

Summit takes a recording, or several recordings of the same conversation, and
returns a speaker-labelled transcript with word-level timestamps plus a written
document in whichever format the meeting called for. It runs the entire pipeline
locally on an NVIDIA GPU: FFmpeg decodes to mono 16 kHz, faster-whisper
transcribes through CTranslate2, WhisperX aligns words against a language-specific
wav2vec2 model, pyannote detects speaker turns, and a local model served by
Ollama writes the notes. Models load one at a time and are freed between stages,
so a 6–10 GB consumer card handles work that would normally imply a workstation.

### 2.2 Capability inventory (all verified in the codebase)

These are the specifics that make marketing copy credible. Vague claims lose to
competitors; enumerated ones win.

| Area | Detail |
|---|---|
| Transcription models | `medium`, `distil-large-v3`, `large-v3`, plus an in-app catalog for downloading more |
| Alignment | WhisperX wav2vec2, per-language, with automatic segment-level fallback |
| Diarization | pyannote 3.1, automatic / exact / minimum–maximum speaker counts |
| Notes styles | 12 (see below) |
| Transcript exports | 6 — TXT, Markdown, JSON, SRT, WebVTT, CSV |
| PDF themes | 7 — Light, Dark, Sepia, Slate, Midnight, High contrast, Grayscale |
| PDF engines | 2 — ReportLab (default) and WeasyPrint |
| PDF layouts | 8 distinct layouts, including landscape pitch slides and newsletter mastheads |
| Notes context window | 6 settings from 4k to 128k tokens |
| Input formats | MP4, MKV, MOV, AVI, WebM, WAV, MP3, M4A, FLAC, OGG, Opus, AAC |
| Platforms | Windows 10/11 and Linux |

The twelve notes styles are Pure Transcription, Meeting Summary, Pitch Deck,
Internal Newsletter, External Newsletter, Technical Meeting (decision record),
Art Meeting, Design Meeting, Business Meeting, Casual Meeting, Stand-Up Meeting,
and AI Voiced Dialogue. Each has its own prompt pack, its own toggleable output
sections, and its own PDF layout. This is the single most under-marketed asset in
the product: competitors offer "a summary," Summit offers the specific document
your role actually files.

### 2.3 The features that survive a demo

A demo has about ninety seconds of attention. These are the moments that convert,
in priority order:

1. **Drag in a recording, walk away, come back to a formatted PDF.** The whole
   value proposition in one gesture.
2. **The speaker table with talk time.** Rename `SPEAKER_00` to a real name and
   watch it propagate through the transcript, the cache, and the already-written
   notes. Shows the product is a workbench, not a script.
3. **Unplug the network and run it again.** The privacy claim, demonstrated
   rather than asserted. This should be a video.
4. **Switch notes style and re-generate from the cached transcript.** Same
   recording, five different documents, no re-processing. Shows depth.
5. **The GPU meter during a large-v3 run.** Establishes technical credibility with
   the r/LocalLLaMA audience instantly.

### 2.4 Honest limitations to state publicly

Stating these builds more trust than hiding them, and pre-empts the refund
requests and one-star reviews that follow overpromising.

- Diarization is probabilistic clustering, not voice identification. It answers
  "who spoke when," not "who is this person."
- Crosstalk, telephone audio, music, and heavy reverberation degrade accuracy.
- An NVIDIA GPU is effectively required. CPU mode exists via the CLI but is slow
  enough that it is not a real product experience.
- macOS is not supported. **(Recommendation:** say so on the pricing page rather
  than letting Mac users discover it after downloading.)
- Some languages have no supported alignment model, and fall back to
  segment-level timestamps.

---

## 3. The market

### 3.1 Why this market is moving now

Four conditions arrived at roughly the same time, and they are the reason a
local-first product can win today when it could not have three years ago.

**Consumer GPUs became inference machines.** An RTX 3060 with 12 GB is a
mainstream card, and it runs `large-v3` comfortably. The hardware prerequisite
that used to disqualify local AI is now sitting under millions of desks.

**Open models caught up.** Whisper large-v3 is competitive with commercial ASR.
pyannote 3.1 is competitive with commercial diarization. Local 7–9B language
models write a genuinely usable meeting summary. The quality excuse for cloud is
gone for this workload.

**Meeting-recording anxiety became a board-level topic.** Every organisation now
has an AI notetaker joining calls, and every legal and compliance team has
started asking where the recordings go, how long they are retained, whether they
train models, and which subprocessors touch them. Many of those questions do not
have comfortable answers.

**Regulation caught up to the anxiety.** GDPR treats voice as personal data and
often as biometric data. HIPAA requires a BAA with any vendor touching PHI. The
EU AI Act adds transparency obligations. Multiple US states require two-party
consent for recording. Every one of these is easier to satisfy when the file
never leaves the laptop.

### 3.2 Bottom-up sizing

Top-down "the transcription market is $X billion" figures are useless for a
one-person desktop product. Here is a bottom-up estimate instead, stated with its
assumptions so it can be challenged.

**Reachable audience (Windows/Linux, NVIDIA GPU, records conversations regularly,
privacy-sensitive or cost-sensitive):**

| Segment | Estimated reachable population | Basis |
|---|---|---|
| Qualitative researchers and academics | 150,000–300,000 | NVivo/ATLAS.ti/MAXQDA user base plus graduate researchers who transcribe interviews |
| Independent podcasters (Windows) | 200,000–400,000 | Active shows publishing monthly, Windows-majority production |
| Journalists and documentary producers | 50,000–100,000 | Source-protection requirement makes cloud unacceptable |
| Legal — small firms, paralegals, court reporters | 100,000–200,000 | Deposition and client-interview handling |
| Healthcare, clinical, and therapy practice | 100,000–250,000 | Session notes; HIPAA-constrained |
| Corporate knowledge workers with local-only policies | 200,000–500,000 | Defence, finance, government contractors |
| Local-AI enthusiasts and homelabbers | 100,000–200,000 | r/LocalLLaMA and r/selfhosted overlap |

That is roughly **900,000 to 2,000,000 reachable individuals**. At a $79 price
and a deliberately modest 0.1% lifetime penetration, that is $70,000–$160,000 in
personal licences. The consumer tier alone is a lifestyle business, not a
venture outcome — which is exactly why the business tier matters.

**Business tier sizing:** if 2,000 organisations globally have a documented
"no cloud transcription" policy and a real recording workload, and Summit reaches
1% of them at an average of $6,000, that is $120,000 annually and it compounds
through renewals and seat expansion. This is where the plan concentrates effort
after month six.

### 3.3 Where the money currently goes instead

Understanding the budget Summit displaces sharpens the pitch:

- **Cloud subscriptions:** $10–$30 per user per month, forever, and rising.
- **Human transcription services:** $1.00–$2.50 per audio minute. A one-hour
  interview costs $60–$150. Researchers with a fifty-interview study are spending
  $3,000–$7,500 and waiting days.
- **Internal staff time:** the most common and least measured. Someone on payroll
  spending 90 minutes writing up a 60-minute meeting.
- **Enterprise on-premise ASR:** five and six figures annually, sold through
  procurement cycles measured in quarters.

Against the researcher's $3,000 transcription budget, a $79 one-time licence is
not a purchase decision. It is an arithmetic result. That comparison should
appear on the pricing page.

---

## 4. Competitive landscape

### 4.1 The four competitive quadrants

**Cloud meeting assistants** — Otter.ai, Fireflies, Fathom, tl;dv, Read.ai, Grain,
plus Zoom AI Companion, Microsoft Teams Copilot, and Google Meet's built-in
notes. Enormous distribution, excellent polish, subscription pricing, and a
fundamental architecture that requires uploading the conversation. They win on
convenience and on calendar integration. They cannot win a conversation about
data residency, and the platform-bundled ones are increasingly the default, which
compresses the standalone players.

**Cloud transcription services** — Rev, Sonix, Trint, Happy Scribe, Descript,
Notta. Per-minute or per-seat pricing, strong editors, good accuracy. Descript in
particular is a genuinely strong product for podcasters and is Summit's most
credible competitor for that segment on features — but it is cloud, subscription,
and Mac-favoured.

**Local and open-source tools** — MacWhisper, Aiko, VoiceInk, and superwhisper on
macOS; Buzz, Vibe, WhisperDesktop, Subtitle Edit, and noScribe cross-platform.
MacWhisper is the proof that this business model works: a polished one-time-purchase
local Whisper app with a devoted user base. The critical observation is that
**MacWhisper and nearly all of its quality-tier peers are macOS-only.** On
Windows, the local options are free open-source tools with rough interfaces,
inconsistent diarization support, and no document generation.

**Enterprise and self-hosted ASR** — Speechmatics, Deepgram self-hosted, NVIDIA
Riva, Verbit. Genuinely private deployments, genuinely expensive, sold to IT
departments rather than to the person with the recording. They do not compete for
the individual researcher or the five-person law firm.

### 4.2 The gap Summit occupies

Summit is the only product that is simultaneously: Windows-first, fully local,
diarization-capable, document-generating, and available as a one-time purchase
without a procurement cycle.

| | Local | Windows | Diarization | Writes documents | One-time price |
|---|---|---|---|---|---|
| **Summit** | Yes | Yes | Yes | 12 styles | Yes |
| Otter / Fireflies / Fathom | No | Yes | Yes | Summary | No |
| Descript | No | Yes | Yes | Limited | No |
| Rev / Sonix / Trint | No | Yes | Yes | Limited | Per minute |
| MacWhisper | Yes | **No** | Yes | Limited | Yes |
| Buzz / Vibe | Yes | Yes | Partial | **No** | Free |
| noScribe | Yes | Yes | Yes | **No** | Free |
| Speechmatics / Riva | Yes | Yes | Yes | No | Enterprise |

### 4.3 Competitive strategy per quadrant

**Against cloud assistants:** do not compete on convenience; you will lose. Compete
on the question their sales teams dread. Every piece of comparison content should
end at the same place: *"Ask your vendor for their subprocessor list and their
data-retention default. Then ask yourself whether you want to keep asking that
question every year."*

**Against MacWhisper:** do not attack it. It is a well-liked product in an adjacent
platform, and its users are proof of demand. Position explicitly as *"the local
transcription app Windows never got,"* and target the search demand that already
exists for "MacWhisper for Windows." That is free, high-intent traffic from people
who have already decided they want this category.

**Against free open-source tools:** compete on finish and on time. The buyer is
someone whose hour is worth more than $79. The message is not "we are better
software," it is "we are the version you do not have to configure." Be genuinely
respectful — Summit is built on the same open-source stack, and the local-AI
community will punish disrespect toward it instantly.

**Against enterprise ASR:** compete on procurement friction. Summit is a download
and a card payment; they are a six-month evaluation. Target the department that
needs this now and cannot wait for IT.

---

## 5. Segments and ideal customer profiles

Six segments are worth naming. They are ranked by expected return on marketing
effort, not by size.

### 5.1 Primary — The qualitative researcher

**Who:** academic, UX, or market researcher running interviews and focus groups.
Often a graduate student or a small research team. Windows workstation, frequently
with a decent GPU for other reasons.

**Why they buy:** they have a real, quantified transcription budget and an ethics
board that has already asked where the audio goes. Institutional review boards
increasingly reject cloud transcription for human-subjects data outright.

**The pitch:** *"Your IRB approved local processing. Summit is local processing. A
fifty-interview study costs you $79 instead of $5,000, and no consent form has to
mention a third party."*

**Where they are:** r/QualitativeResearch, r/AskAcademia, r/GradSchool, methods
blogs, NVivo and ATLAS.ti user communities, university research-computing mailing
lists, conference posters.

**Why they rank first:** highest pain, clearest budget comparison, strongest
word-of-mouth inside departments, and a compliance requirement that structurally
excludes the cloud competition.

### 5.2 Primary — The compliance-constrained professional

**Who:** solo and small-firm lawyers, paralegals, therapists and clinicians, HR
investigators, financial advisers, and government contractors.

**Why they buy:** they are not choosing Summit over Otter. They are choosing
Summit over *typing it themselves,* because their professional obligations
forbid the cloud option. This is the least price-sensitive and least
churn-prone segment in the plan.

**The pitch:** *"Privileged, confidential, or protected material never leaves the
device. There is no BAA to negotiate, because there is no vendor to sign one
with."*

**Where they are:** r/LawFirm, r/legaltech, r/therapists, r/HealthIT, state bar
technology sections, practice-management newsletters, legal-technology podcasts.

**Note:** this segment converts into the business tier. A solo practitioner who
buys a personal licence is the beachhead into their firm.

### 5.3 Primary — The independent podcaster and video producer

**Who:** independent creators producing episodic multi-speaker content who need
transcripts for show notes, SEO, subtitles, and repurposing.

**Why they buy:** volume economics. Weekly two-hour episodes make per-minute
pricing painful, and subscription pricing feels like renting a tool they use
constantly. Summit's SRT and WebVTT export plus speaker labels feeds directly
into their existing workflow.

**The pitch:** *"Weekly show, two hours, two hosts, one guest. Summit costs you
once. Everyone else charges you every month, forever."*

**Where they are:** r/podcasting, r/podcast, r/VideoEditing, podcaster Discords
and Facebook groups, podcast-technology newsletters.

### 5.4 Secondary — The local-AI enthusiast

**Who:** the r/LocalLLaMA reader with an RTX 4090 who already runs Ollama.

**Why they matter more than their purchase volume suggests:** they are the
distribution channel. They will scrutinise the stack, and if it holds up they
will recommend it to everyone else on this list. They also generate the
early technical credibility that makes the business tier's security questionnaire
easy to answer.

**The pitch:** technical and unvarnished. faster-whisper, WhisperX, pyannote 3.1,
your own Ollama models, sequential model loading, automatic CUDA OOM fallback,
full CLI. Show the architecture; do not market at them.

**Where they are:** r/LocalLLaMA, r/selfhosted, r/homelab, Hacker News, the Ollama
Discord.

### 5.5 Secondary — The journalist and documentarian

**Who:** investigative reporters, documentary producers, oral-history projects.

**Why they buy:** source protection is not a preference. Uploading a whistleblower
interview to a third party is a professional failure.

**Where they are:** r/Journalism, Investigative Reporters and Editors, journalism
technology newsletters, press-freedom organisations.

**Note:** small segment, disproportionate press value. A single journalist writing
about the tool reaches all the other segments at once.

### 5.6 Growth — The enterprise business unit

**Who:** a team of five to fifty inside a larger organisation whose security policy
prohibits cloud transcription — defence contractors, banks, hospitals, government
departments, pharmaceutical companies.

**Why they buy:** they have the problem, the budget, and no acceptable option.
They are currently either not transcribing at all or doing it manually.

**How they buy:** an individual finds Summit, uses the trial, and brings it to
their team. Land-and-expand, not outbound. The marketing job is to be findable
and to make the security review painless.

---

## 6. Positioning and messaging

### 6.1 Positioning statement

> For professionals who record conversations they cannot upload, Summit is a
> desktop transcription and meeting-notes application that runs entirely on the
> user's own computer. Unlike Otter, Fireflies, and every other AI notetaker,
> Summit has no server, no account, and no vendor holding the recording — which
> means the privacy question is answered by the architecture rather than by a
> policy document.

### 6.2 The message hierarchy

Everything below ladders up to one line, which the website already gets right:

> **Every voice. Every word. Never the cloud.**

Three supporting pillars, in the order they should appear in almost every piece of
material:

**Pillar 1 — Privacy is structural, not promised.**
There is no upload, no account, and no subprocessor. After the first model
download, the application runs with the network disconnected. The strongest
privacy policy is not having a server. *Proof:* run it in airplane mode on video;
publish the network-activity documentation; point to the source of every model
used.

**Pillar 2 — It writes the document, not just the transcript.**
Twelve notes styles, each producing the artefact the meeting was supposed to
produce: a decision record, a stand-up digest, a pitch outline, a customer-safe
newsletter, a formatted PDF. *Proof:* side-by-side sample PDFs of the same
recording rendered in four different styles.

**Pillar 3 — You buy it once.**
A perpetual licence on your own hardware, with no per-minute meter and no seat
count that grows with headcount. *Proof:* a five-year cost comparison against the
three leading subscriptions.

A fourth pillar is available for technical audiences: **it is serious
engineering** — sequential model loading, automatic CUDA OOM fallback through
batch size, model size, and CPU offload, word-level alignment with graceful
degradation, cancel-safe stages, and a transcript cache that lets you re-generate
notes without re-transcribing.

### 6.3 Message by segment

| Segment | Lead message | Emotional driver |
|---|---|---|
| Researcher | Your IRB already approved this architecture | Relief from an approvals problem |
| Legal / clinical | Privilege and PHI never leave the device | Fear of a disclosure incident |
| Podcaster | Buy it once, transcribe forever | Resentment of subscription creep |
| Local-AI enthusiast | faster-whisper, WhisperX, pyannote, your own Ollama models | Pride in owning the stack |
| Journalist | Your source's voice stays on your machine | Professional duty |
| Enterprise | The recording never leaves the building | Risk elimination |

### 6.4 Objection handling

| Objection | Response |
|---|---|
| "I need an NVIDIA GPU?" | Yes, 6 GB or more. That is a $250 card or the one already in most gaming and workstation PCs. Publish a tested-hardware list with real timings so people can self-qualify in ten seconds. |
| "Cloud tools are more accurate." | They are running comparable models. Summit uses Whisper large-v3 and pyannote 3.1. Publish a reproducible benchmark on public audio rather than asserting parity. |
| "Setup looks complicated." | The honest answer today is that it is. See §9 — this must be fixed, not argued with. |
| "$79 is a lot for something built on free models." | You are buying the integration, the interface, the twelve document styles, and the twenty hours you would spend assembling it yourself. Buzz and noScribe are excellent and free; recommend them openly to people who want to configure things. |
| "Why no Mac?" | Not yet. Say it plainly on the site. Collect Mac emails separately so the demand is measurable. |
| "What if you go out of business?" | The software runs locally and keeps working. Nothing is revoked. **(Recommendation:** commit publicly to publishing a licence-free build if the project is ever abandoned. Cheap to promise, extremely persuasive.) |
| "Can I try it on real data?" | Yes — full features, ten-minute files, no card, no account. |

### 6.5 Words to use and avoid

**Use:** local, on your own computer, no upload, no account, never leaves the
device, buy it once, speaker labels, word-level timestamps, finished document.

**Avoid:** "military-grade encryption" (there is no encryption claim to make —
the data does not move), "AI-powered" (meaningless in 2026), "revolutionary,"
"seamless," and any claim of HIPAA or GDPR *compliance*. Summit is a tool that
makes compliance easier; the customer's deployment is what is or is not compliant.
Say "supports your compliance obligations," never "HIPAA compliant." This
distinction matters legally.

---

## 7. Pricing and packaging

### 7.1 Current state (fact)

The website carries placeholder pricing: Trial free with a ten-minute per-file
limit, Personal $79 one-time for one computer, Team $249 one-time for five
computers, Business "talk to us." None of this is enforced in the application —
there is no trial limit, no licence key, and no payment flow.

### 7.2 Analysis of the current tiers

**The trial is well-designed.** Full features with a length cap is exactly right
for this product. It lets a researcher process a real interview excerpt and a
podcaster process a real segment. Nothing is watermarked or withheld, which
matters enormously for trust in a privacy-positioned product. Keep it.

**Personal at $79 is defensible but slightly low.** MacWhisper Pro anchors the
category around $59, but Summit does more — diarization, twelve document styles,
PDF generation. The buyer comparison is not MacWhisper, it is a $20/month
subscription. At $79 the payback is four months.

**Team at $249 for five machines is mispriced.** That is $49.80 per seat, 37%
below the single-seat price, which is a steeper volume discount than five seats
justifies and it cannibalises pairs and trios who would happily pay more.

**Business "talk to us" is correct** and is where the plan expects most revenue.

### 7.3 Recommended pricing

| Tier | Price | Terms | Rationale |
|---|---|---|---|
| **Trial** | Free | Full features, 10-minute files, no card, no account | Unchanged. It works. |
| **Personal** | **$99** | One-time, 2 machines, 12 months of updates, perpetual fallback | Round, premium, still trivially justified against any subscription |
| **Team** | **$349** | One-time, 5 machines, 12 months of updates, priority support | $69.80/seat — a real discount that does not undercut Personal |
| **Business** | **From $2,500/yr** | Site or seat-band licence, deployment documentation, security-questionnaire support, named contact | Priced against the alternative, which is an enterprise ASR contract |
| **Education** | **$49 / $199** | Personal and Team, verified `.edu` | Captures the researcher segment at their real budget and buys enormous word of mouth |

Two structural recommendations attached to this:

**Adopt the perpetual-fallback licence model.** The customer gets twelve months of
updates and keeps forever whatever version shipped inside that window. Renewal is
optional and discounted, historically around 40–50% of new price. This is the
Sublime Text and JetBrains model. It preserves the "buy it once" message that this
audience specifically wants while creating a recurring revenue line that funds
continued development. Without it, a one-time price means every future release is
unfunded work.

**Price the Business tier annually, not perpetually.** Business buyers are more
comfortable with an annual line item than a capital purchase, it survives
procurement more easily, and it aligns support obligations with revenue.

### 7.4 Positioning the price

The pricing page should not defend $99. It should make $99 look like an
accounting error in the customer's favour, by showing what they are doing today:

| What they use now | Five-year cost |
|---|---|
| Otter Pro at ~$17/month | ~$1,020 |
| Rev human transcription, 4 hours/month | ~$14,400 |
| A cloud notetaker at ~$25/month | ~$1,500 |
| **Summit Personal** | **$99, plus optional renewals** |

Add the researcher's line explicitly: *"A fifty-interview study at $1.50 a minute
costs $4,500 to transcribe. Summit costs $99 and finishes overnight."*

### 7.5 What must be built to charge money (blocker)

- Licence key generation, delivery, and offline-capable validation. Offline
  validation is non-negotiable — an air-gapped licence check would contradict the
  entire product promise. Use signed licence files verified locally, with no
  phone-home.
- Trial enforcement: a ten-minute per-file media-duration check before processing.
- Payment and tax handling. **Recommendation:** use a merchant of record —
  Paddle, Lemon Squeezy, or FastSpring — rather than raw Stripe. They handle VAT,
  sales tax, and global compliance, which is a genuine multi-week burden for a
  solo operation selling internationally.
- Machine-transfer flow, since "move your licence between machines" is already
  promised on the site.

---

## 8. The funnel and the conversion model

### 8.1 Funnel stages

```
Awareness      → Reddit, HN, YouTube, SEO, press
Consideration  → Website, demo video, sample PDFs, privacy page
Trial          → Download → Install → First run
Activation     → First successful transcript with speaker labels   ← the critical gate
Value          → First generated notes document
Purchase       → Hits the ten-minute limit on real work
Expansion      → Recommends to team → Business tier
```

### 8.2 Activation is the whole game

Every other number in this plan is downstream of one metric: **the percentage of
people who download Summit and successfully produce their first transcript.**

Current first-run sequence: install the application, install FFmpeg separately and
put it on PATH, verify an NVIDIA driver, create a Hugging Face account, generate a
read token, accept the terms on `pyannote/speaker-diarization-3.1`, possibly also
accept `pyannote/segmentation-3.0`, paste the token into settings, then optionally
install Ollama and pull a model before any notes can be written.

That is seven to nine steps across three external websites before the first word
of output. For a developer tool that is acceptable. For a $99 product marketed to
researchers, lawyers, and podcasters it is fatal — a realistic activation rate for
that sequence is 10–20%.

**Recommendation — the single highest-leverage change in this entire plan:** build
a first-run wizard that reduces this to one screen and one external step.
Specifically: bundle an LGPL FFmpeg build with the installer (with proper licence
compliance) or download it automatically on first run; detect the GPU and driver
and report clearly what was found; walk the user through the Hugging Face token
with an embedded browser and deep links to the exact "accept terms" pages, with
live validation of the pasted token; offer an optional one-click Ollama install
and model pull; and ship a fifteen-second sample recording so the user can produce
a real transcript inside two minutes of launching the app.

Moving activation from 15% to 50% multiplies revenue by 3.3× with zero additional
traffic. No channel investment in this document comes close to that return.

### 8.3 Target conversion rates

| Stage | Conservative | Target | Note |
|---|---|---|---|
| Visitor → trial download | 3% | 6% | Strong demo video is the main lever |
| Download → install | 70% | 85% | Signed installer; unsigned binaries lose Windows users to SmartScreen |
| Install → first transcript | 15% | 50% | The wizard; see §8.2 |
| Activated → notes generated | 40% | 65% | Ollama friction; ship a default model path |
| Activated → purchase | 8% | 15% | Ten-minute limit hit on real work |
| Purchase → business referral | 2% | 5% | In-app "using this at work?" prompt |

At 25,000 first-year visitors, target rates produce roughly 1,500 downloads, 640
activations, and 96 sales — which is short of the 900-licence goal. **The plan
therefore needs 120,000–150,000 first-year visitors, or better conversion.**
That traffic requirement drives everything in §11.

---

## 9. Launch blockers

Nothing in this plan can generate revenue until these close. They are ordered by
sequence dependency.

| # | Blocker | Why it blocks | Owner | Estimate |
|---|---|---|---|---|
| 1 | **No LICENSE file exists in the repository** | There is no stated legal basis on which anyone may use or buy the software. An EULA is required before the first sale. | Legal | 1 week |
| 2 | **Qt/PySide6 licensing not addressed** | PySide6 is LGPLv3. Selling proprietary software built on it requires either documented LGPL compliance — dynamic linking, licence notices, and the ability for users to relink against a modified Qt — or a Qt commercial licence. The PyInstaller one-folder build helps, but compliance must be deliberate and documented. | Legal + eng | 2 weeks |
| 3 | **No third-party licence inventory** | A business buyer's security questionnaire will ask for one. So will any reseller. Needs a NOTICE file covering faster-whisper, WhisperX, pyannote, PySide6, WeasyPrint, ReportLab, PyTorch, CUDA runtime libraries, Space Grotesk (SIL OFL), and every bundled model. | Legal | 1 week |
| 4 | **pyannote model terms and commercial use** | The diarization models are gated behind terms acceptance on Hugging Face. Confirm in writing that commercial use of the model weights by end users is permitted, and document what each customer must accept. This is a core feature; it cannot rest on an assumption. | Legal | 1–2 weeks |
| 5 | **No Windows installer** | The download page currently shows a waitlist. There is no product to download. | Eng | 2 weeks |
| 6 | **Installer is not code-signed** | An unsigned installer triggers Windows SmartScreen, which is a large silent loss for a security-positioned product. An EV or OV certificate is ~$200–$400/year and reputation must accrue. Start early. | Eng | 1 week + lead time |
| 7 | **No trial enforcement** | The ten-minute limit exists only in website copy. | Eng | 3 days |
| 8 | **No licence system** | No key generation, delivery, or offline validation. | Eng | 2 weeks |
| 9 | **No payment flow** | Merchant-of-record account, checkout, receipts, tax. | Ops | 1 week |
| 10 | **First-run onboarding wizard** | The activation problem in §8.2. Technically optional, commercially decisive. | Eng | 3 weeks |
| 11 | **Demo video does not exist** | The single highest-converting asset on any software landing page. | Marketing | 1 week |
| 12 | **No privacy verification artefact** | The central claim needs evidence — published network documentation, and ideally a third-party or community audit. | Marketing | 1 week |

**Critical path:** items 1–4 are legal and can run in parallel with engineering.
Items 5–9 are the minimum to accept money. Item 10 determines whether the money
is worth accepting. Realistic runway to a sellable product: **eight to ten weeks.**

---

## 10. Launch plan

Anchored to a public launch in **late October 2026**.

### Phase 0 — Foundation (mid-August to late September, 6 weeks)

Close the blockers. In parallel, build the launch assets so nothing is written
under deadline pressure:

- Record the primary demo video: two minutes, drag-to-PDF, ending with the network
  disconnected and the app still working.
- Produce sample outputs — the same recording rendered as Meeting Summary,
  Technical Decision Record, Pitch Deck, and Newsletter PDFs, downloadable without
  an email gate.
- Write the benchmark post: accuracy and speed on public audio across several GPUs,
  with reproducible method and honest results including where Summit is weaker.
- Publish the hardware compatibility table with real timings.
- Recruit 20–30 private beta users, drawn deliberately from all six segments, with
  a structured feedback form and an explicit ask for a testimonial.
- Stand up analytics that do not contradict the positioning: **self-hosted Plausible
  or Umami on the website, and no telemetry whatsoever in the application.** A
  privacy product that phones home is a scandal waiting to be found. Measure
  activation through an optional, clearly labelled, off-by-default survey instead.
- Begin building the launch list. Target 500 emails before launch day.

**Exit criteria:** installer signed and downloadable, trial enforced, payment live,
EULA published, ten beta testimonials collected, 500 emails on the list.

### Phase 1 — Soft launch (first two weeks of October)

Ship quietly to the launch list and the beta cohort. Fix what breaks. Watch the
activation number obsessively — if it is below 40%, delay the public launch and
fix onboarding. Publishing to Hacker News with a broken first run wastes the one
shot at that audience.

**Exit criteria:** activation above 40%, at least 20 paid customers, no critical
bugs open.

### Phase 2 — Public launch (last two weeks of October)

A coordinated week, not a single day:

- **Monday:** Show HN — *"Show HN: Summit – local transcription with speaker
  labels that never uploads your audio."* Post at 08:00–10:00 ET on a Tuesday or
  Wednesday for best results; be present in the comments all day. This audience
  will interrogate the stack, and answering well is the marketing.
- **Tuesday:** Product Hunt launch, with the launch list mobilised.
- **Wednesday:** r/LocalLLaMA post, written as a technical build write-up rather
  than an advertisement, disclosing commercial interest in the first line.
- **Thursday:** r/selfhosted and r/podcasting, each with segment-specific framing.
- **Friday:** publish the benchmark post and submit it to the aggregators.
- **Throughout:** press outreach to privacy, local-AI, and Windows-software
  publications, and to the journalism-tools newsletters.

**Target:** 15,000 visitors, 900 downloads, 60 sales in launch week.

### Phase 3 — Compounding (November 2026 to April 2027)

Shift from launch spikes to durable acquisition. Publish two substantial pieces
per month against the SEO map in §12. Run the segment-specific campaigns in §11
sequentially, one segment per month, so each gets real attention. Begin the
business-tier motion in §13. Ship visible product improvements monthly, because
"actively developed" is itself a purchase argument for perpetual licences.

**Target by end of April:** 8,000 monthly organic visitors, 400 cumulative
licences, first five business agreements.

### Phase 4 — Enterprise focus (May 2027 onward)

Once the consumer funnel is self-sustaining, redirect effort to the business tier
where the revenue concentration is. Build the compliance collateral set, pursue
conference presence in legal technology and clinical informatics, and formalise
the land-and-expand path from individual users into their organisations.

---

## 11. Channel playbooks

### 11.1 Reddit — the highest-return channel

Reddit is where every segment in this plan already congregates, and privacy-first
local software is one of the few genuinely welcome commercial topics there.

The rules matter more than the tactics. Participate for weeks before posting
anything promotional. Disclose commercial interest in the first line, every time.
Lead with technical substance. Answer criticism directly, including when it is
right. Never use a second account. One bad post in r/LocalLLaMA will outrank the
website in search results for years.

| Subreddit | Angle | Cadence |
|---|---|---|
| r/LocalLLaMA | Architecture, benchmarks, VRAM management, OOM fallback | Monthly, technical |
| r/selfhosted | No cloud, no account, no telemetry | Every 6 weeks |
| r/podcasting | Show notes and subtitles without a subscription | Monthly |
| r/QualitativeResearch | Interview transcription, IRB, cost per study | Monthly |
| r/Journalism | Source protection | Quarterly |
| r/therapists, r/LawFirm, r/legaltech | Confidentiality, privilege, PHI | Quarterly, careful |
| r/homelab, r/DataHoarder | Archive processing at scale | Occasional |

### 11.2 Hacker News

One Show HN at launch, then earn attention through content rather than
announcements. The posts that work from this project are the engineering ones:
how sequential model loading keeps a three-model pipeline inside 8 GB; what
automatic CUDA OOM fallback actually has to handle; why word-level alignment
fails and what to do about it; a real accuracy comparison of Whisper against
commercial ASR. Never submit your own landing page. Submit the technical writing
and let it carry the product.

### 11.3 SEO — the compounding asset

This is the channel that still delivers in year two. The keyword map divides into
four clusters:

**Category intent** — "local transcription software", "offline transcription
software", "transcribe audio without uploading", "private transcription software",
"transcription software with speaker labels", "offline speech to text Windows".

**Competitor intent** — "Otter.ai alternative privacy", "Fireflies alternative
self-hosted", "MacWhisper for Windows", "Descript alternative one-time purchase",
"Rev alternative software", "free Otter.ai alternative". These convert better than
anything else because the searcher has already decided to leave a product.

**Compliance intent** — "HIPAA transcription software", "GDPR compliant
transcription", "transcription for legal depositions", "IRB approved transcription",
"attorney-client privilege transcription". Low volume, extremely high value, and
the exact doorway into the business tier.

**Technical intent** — "whisper diarization GUI", "WhisperX Windows GUI",
"pyannote speaker diarization software", "faster-whisper desktop app", "Ollama
meeting notes". These bring the local-AI segment.

The content strategy is one substantial page per cluster entry, each genuinely
useful whether or not the reader buys — comparison pages that fairly describe the
competitor, how-to guides that work with free tools too, and compliance pages that
explain the actual regulation rather than fearmongering.

### 11.4 YouTube and video

Video is where a local application's value is obvious and where the privacy claim
becomes visible. Six videos worth making, in order:

1. The two-minute demo (landing page hero).
2. "Transcribing with the network cable unplugged" — the privacy proof, and the
   most shareable thing this project can produce.
3. Full walkthrough: a real one-hour meeting from drag to finished PDF.
4. All twelve notes styles, same recording, side by side.
5. Hardware and speed: what a 3060, 4070, and 4090 actually do.
6. Setup guide, which doubles as support deflection.

Then pursue placement with the local-AI, privacy, and Windows-productivity
channels. Offer licences freely to reviewers with no conditions attached — the
credibility of an unconditioned review is worth more than a controlled message.

### 11.5 Directories, listings, and communities

Cheap, one-time, and durable: AlternativeTo (target the Otter, Descript, and
Fireflies pages specifically), Product Hunt, Slant, SaaSHub, Privacy Tools
listings, the awesome-selfhosted and awesome-privacy lists, the Ollama community
showcase, and Hugging Face Spaces or a model-card mention where the stack is
relevant. Each takes an hour and pays out for years.

### 11.6 Partnerships

Three worth real effort:

**NVIDIA.** They actively promote polished local applications that showcase RTX
inference. A well-built Windows app running a three-model pipeline on consumer
hardware is exactly their story. Their developer programs and RTX AI showcases
represent large, free, credible distribution.

**Ollama.** Summit is a genuine, non-trivial Ollama integration with twelve prompt
packs. Community showcase placement and cross-promotion cost nothing and reach
precisely the right people.

**Qualitative research software.** NVivo, ATLAS.ti, and MAXQDA users need
transcripts and their vendors do not solve it well. Integration content — "how to
get Summit transcripts into NVivo" — reaches a segment with budget and no good
option.

### 11.7 Paid acquisition

**Recommendation: stay out of paid search initially.** Otter, Rev, and Descript
are well funded and the transcription keywords are expensive. A small budget will
be consumed without learning much.

Where a modest budget does work: retargeting people who visited the pricing page
but did not download, at $200–400/month; a small experiment on the compliance
keyword cluster, which the big players largely ignore and where a $2,500 business
deal justifies a high cost per click; and sponsorship of two or three
narrowly-targeted newsletters — a legal-technology digest, a qualitative-methods
newsletter, a local-AI newsletter — which typically outperform display advertising
by a wide margin for products like this.

---

## 12. Content plan

### 12.1 Editorial principles

Every piece should be useful to a reader who never buys anything. That is not
altruism; it is what earns links, community goodwill, and search rankings. Three
rules: show real output rather than describing it, publish honest numbers
including unflattering ones, and never write a comparison that misrepresents a
competitor — the audience will check, and being caught costs more than the
comparison earns.

### 12.2 Cornerstone content

Six pieces that get updated rather than replaced:

1. **"Where your meeting recordings actually go."** A researched survey of the
   published data-handling terms of the major cloud notetakers — retention
   defaults, subprocessor lists, training-data clauses, enterprise carve-outs.
   Rigorous, sourced, and factual, with no editorialising. This is the piece that
   gets shared inside companies and quoted by journalists.
2. **"Local transcription accuracy, measured."** Whisper large-v3 and pyannote 3.1
   against the commercial services on public audio, with reproducible method,
   published scripts, and honest reporting of where local loses.
3. **"The complete guide to transcribing research interviews privately."** The
   segment cornerstone for researchers, covering IRB language, consent forms,
   and workflow — useful with free tools too.
4. **"Speaker diarization explained."** What it is, what it is not, why it fails,
   and how to read the output. Educational, ranks well, and pre-empts the most
   common support complaint.
5. **"What an NVIDIA GPU actually costs to run local AI."** Hardware guidance with
   real numbers, which qualifies buyers before they download.
6. **"Buy once, or rent forever."** The five-year cost analysis, updated annually.

### 12.3 Ninety-day calendar

| Month | Publishing | Campaign focus |
|---|---|---|
| Month 1 (launch) | Demo video, benchmark post, "Where your recordings go", launch posts | Broad awareness |
| Month 2 | Research-interview guide, diarization explainer, Otter comparison, first customer story | Researchers |
| Month 3 | Podcast workflow guide, notes-styles video, hardware guide, MacWhisper-for-Windows page | Podcasters |
| Month 4 | Legal and clinical compliance pages, security-questionnaire FAQ, second customer story | Compliance segment |

### 12.4 Social proof to collect from day one

Testimonials from each segment, named where permitted. Screenshots of real output
with permission. A public changelog, because visible development is a purchase
argument. Support responsiveness, publicly visible — for a privacy product sold by
a small team, "the developer answers email in a day" is a genuine differentiator
worth advertising.

---

## 13. Business tier sales motion

### 13.1 How these deals actually start

They do not start with outbound. They start with one person inside an organisation
downloading the trial because their compliance team blocked Otter. The entire
motion is: be findable when that person searches, make their internal case easy to
make, and be easy to buy from once they have made it.

### 13.2 The collateral that closes these deals

- **A security and architecture brief.** One document: data flow, network activity,
  what leaves the machine and when (model downloads only), storage locations,
  logging and token redaction, and the third-party licence inventory. Most
  security reviews are satisfied by a good version of this document alone.
- **A pre-answered security questionnaire.** SIG Lite and CAIQ formats. Most
  answers are trivially favourable because there is no cloud service, and saying
  so in their format saves weeks.
- **A compliance mapping note.** How local processing supports GDPR Article 9
  obligations, HIPAA's requirements around PHI and business associates, and
  jurisdictional data-residency requirements. Framed as support for the customer's
  obligations, never as a compliance claim by Summit.
- **A deployment guide for locked-down networks.** How to pre-stage model files,
  operate without internet access after setup, and deploy across machines.
- **A one-page internal business case** the champion can forward to their manager,
  with the cost comparison and the risk argument already written.

### 13.3 Pricing and process

Anchor at $2,500 annually for up to ten seats, scaling by seat band, with a site
licence above roughly fifty seats. Offer a thirty-day evaluation without the
ten-minute limit, delivered as a time-limited licence file. Expect a sixty to
ninety day cycle. Ask every business customer for two things at signature: a
reference call commitment and an introduction to one peer organisation.

### 13.4 Where to be present

Legal technology conferences, clinical informatics events, qualitative research
methods conferences, and government IT procurement channels. Start with content
and speaking rather than booths; a conference talk on "keeping recorded interviews
inside your own infrastructure" costs a flight and generates better leads than a
$15,000 exhibition stand.

---

## 14. Metrics

### 14.1 The one number

**Activation rate — downloads that produce a first successful transcript.** If this
is below 40%, no other marketing investment is worth making. Track it through an
optional, off-by-default, clearly-labelled first-run survey rather than telemetry.

### 14.2 Dashboard

| Metric | Cadence | Month 3 target | Month 12 target |
|---|---|---|---|
| Unique website visitors | Weekly | 6,000/mo | 15,000/mo |
| Trial downloads | Weekly | 300/mo | 900/mo |
| Activation rate | Weekly | 45% | 60% |
| Trial → paid conversion | Monthly | 8% | 15% |
| Personal/Team licences sold | Monthly | 30/mo | 90/mo |
| Business agreements | Monthly | 0 | 2/mo |
| Monthly bookings | Monthly | $3,000 | $18,000 |
| Organic search sessions | Monthly | 800/mo | 8,000/mo |
| Launch list size | Weekly | 1,200 | 6,000 |
| Support tickets per 100 activations | Monthly | < 25 | < 10 |
| Refund rate | Monthly | < 5% | < 3% |

### 14.3 Leading indicators worth watching

Time from download to first transcript, which predicts activation. The share of
support tickets that are setup problems, which measures whether the wizard worked.
Which notes styles get used, which tells you what to build next. The share of
traffic arriving on competitor-comparison pages, which measures whether the
positioning is landing.

### 14.4 Kill criteria

Set these now, while judgement is uncontaminated by sunk cost. If after six months
activation is still below 30% despite onboarding work, the product is too hard to
install and the answer is engineering, not marketing. If trial-to-paid is below 4%,
the price or the value proposition is wrong. If organic traffic is below 1,500
monthly sessions after six months of publishing, the SEO thesis has failed and the
budget should move to partnerships and paid newsletters.

---

## 15. Budget

### 15.1 Year one, lean

| Item | Annual |
|---|---|
| Code-signing certificate (OV/EV) | $400 |
| Merchant of record fees (~5% of $180k) | $9,000 |
| Website hosting and analytics | $300 |
| Demo video production | $2,000 |
| Newsletter sponsorships (6 × $500) | $3,000 |
| Retargeting ads | $3,600 |
| Compliance keyword experiment | $2,400 |
| Conference attendance (2 events) | $4,000 |
| Legal — EULA, licence review, Qt compliance | $3,500 |
| Design — assets, PDF templates, screenshots | $1,500 |
| **Total** | **$29,700** |

Against a $180,000 bookings target that is a 16% marketing cost, which is healthy
for a product business. The largest real cost is not in this table — it is the
founder time in Phase 0, and it is entirely engineering.

### 15.2 If the launch works

Reinvest in order: contract technical writing to accelerate the SEO map; a macOS
port, which unlocks the largest segment currently turned away; sponsored placement
with the local-AI YouTube channels; and a part-time salesperson for the business
tier, but only once ten business deals have closed inbound and the motion is
proven.

---

## 16. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Setup friction destroys activation** | High | Critical | The first-run wizard in §8.2. This is the top risk in the plan. |
| **Qt/PySide6 licensing forces a change** | Medium | High | Resolve before launch. Budget for a Qt commercial licence as a contingency, or verify LGPL compliance formally. |
| **pyannote terms restrict commercial use** | Medium | Critical | Confirm in writing now. Identify a fallback diarization path before it is needed. |
| **Windows SmartScreen suppresses downloads** | High initially | Medium | Sign early so reputation accrues; publish hashes; explain the warning on the download page. |
| **A cloud vendor ships a credible local mode** | Low | High | Their business model resists it. Deepen the moat in document generation and Windows-native polish rather than racing on transcription. |
| **Free open-source alternatives improve** | High | Medium | They will, and Summit is built on them. Compete on finish, documents, and support — not on the model layer. |
| **GPU requirement excludes too many buyers** | Medium | Medium | Publish the hardware table prominently so unqualified users self-select out before they are disappointed. |
| **Support load exceeds capacity** | Medium | Medium | Deflect with excellent documentation and setup video; the wizard is also a support investment. |
| **Privacy claim is challenged** | Low | Critical | Never ship telemetry. Publish network documentation. Invite community verification. One contradiction here destroys the brand permanently. |
| **A single founder is the bus factor** | High | High | Publish an abandonment commitment: if development ceases, a licence-free build is released. Turns a risk into a trust signal. |

---

## 17. Immediate next actions

Ordered, with the first five being the only ones that matter this month.

1. **Get a lawyer to draft the EULA and review Qt and pyannote obligations.** Two
   weeks of lead time and nothing can be sold until it is done.
2. **Order the code-signing certificate.** Reputation with SmartScreen accrues
   slowly; every week of delay costs downloads at launch.
3. **Build the first-run wizard.** The highest-return work available in this entire
   document.
4. **Ship the signed installer with trial enforcement.**
5. **Stand up payment through a merchant of record.**
6. Record the two-minute demo video and the network-unplugged privacy video.
7. Produce the four sample PDFs and put them on the site without an email gate.
8. Update the pricing page to the §7.3 structure and add the five-year comparison.
9. Recruit twenty-five beta testers across the six segments.
10. Start participating — genuinely, without promotion — in r/LocalLLaMA,
    r/QualitativeResearch, and r/podcasting, so that launch-week posts come from a
    known account rather than a new one.

---

## Appendix A — Copy bank

**Taglines**
- Every voice. Every word. Never the cloud. *(current, and strong)*
- The transcription app that has nowhere to send your audio.
- Your conversations. Your computer. Nobody else's server.

**Elevator pitch, thirty seconds**
> Summit transcribes meetings, labels who said what, and writes the notes — all on
> your own PC. No upload, no account, no subscription. If your work involves
> conversations you legally cannot put in someone else's cloud, this is the only
> tool on Windows that does the whole job locally. Buy it once.

**One-liner for directories**
> Private, local transcription and meeting notes for Windows and Linux, with
> speaker labels and twelve document styles. Runs entirely on your own GPU.

**Show HN title**
> Show HN: Summit – Local transcription with speaker diarization that never
> uploads your audio

**Reddit opener (r/LocalLLaMA)**
> I built a Windows desktop app around faster-whisper, WhisperX, and pyannote 3.1
> that loads each model sequentially so the whole pipeline fits in 8 GB, and it
> writes meeting notes with whatever Ollama model you already have. Commercial
> product, trial is free, happy to answer anything about the architecture — the
> OOM fallback chain was the hard part.

---

## Appendix B — Launch asset checklist

**Website:** demo video on the hero, four sample PDFs ungated, hardware
compatibility table, five-year cost comparison, security brief linked from
pricing, macOS waitlist capture, updated pricing, working download.

**Video:** two-minute demo, network-unplugged privacy proof, full walkthrough,
twelve-styles comparison, hardware and speed, setup guide.

**Written:** benchmark post, "Where your meeting recordings actually go", three
competitor comparison pages, research-interview guide, diarization explainer,
security and architecture brief, pre-answered SIG Lite and CAIQ, deployment guide.

**Product:** signed installer, first-run wizard, trial enforcement, licence system,
sample recording bundled, in-app "using this at work?" prompt.

**Legal:** EULA, third-party NOTICE file, privacy policy update, Qt compliance
documentation, abandonment commitment.

---

## Appendix C — Trial email sequence

Five emails, sent only to people who opt in at download.

| Day | Subject | Purpose |
|---|---|---|
| 0 | Your Summit download, and the two-minute version | Drive first run immediately |
| 1 | Did it work? | Catch failed activation while intent is alive; one-click reply to a human |
| 3 | Twelve documents from one recording | Reveal the notes styles, the most under-discovered feature |
| 6 | What a fifty-interview study costs | The cost argument, segment-tailored where known |
| 10 | Your ten-minute limit, and what's past it | The purchase ask, once real value has landed |

Every email must be answerable by a human, and every one should carry the same
signature line: *no tracking pixels, and we do not know whether you opened this.*
For this audience, that line does more work than the copy above it.

---

## Appendix D — Assumptions requiring validation

1. Trial-to-paid conversion of 15% at $99. **Validate:** beta cohort willingness-to-pay
   interviews before launch.
2. Compliance buyers will purchase without a formal certification. **Validate:** five
   discovery calls with legal or clinical prospects.
3. Windows local transcription demand is real, not merely a gap on paper.
   **Validate:** search volume for "MacWhisper for Windows" and equivalents.
4. Activation can reach 50% with a wizard. **Validate:** measure before and after with
   the beta cohort.
5. Business deals will arrive inbound rather than requiring outbound. **Validate:** the
   first six months of enquiries.
6. One-time pricing is materially preferred by this audience. **Validate:** offer both
   perpetual and subscription to the beta cohort and observe the split.
