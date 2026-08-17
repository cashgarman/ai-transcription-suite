"""Seeded procedural scenarios: the ground truth a summary is graded against.

A scenario is built entirely from one integer seed, so the same seed always
yields the same participants, topics, facts, and distractors. Nothing here
touches a model; the generator turns a scenario into dialogue afterwards.

Distractors matter as much as facts. A meeting where every idea sticks cannot
distinguish a summary that reports the room accurately from one that reports
everything anyone said, so each scenario plants a few proposals that were
retracted, rejected, or floated hypothetically.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from speaker_transcriber.promptlab.types import (
    Distractor,
    Fact,
    FREEFORM_MODE,
    GROUNDED_MODE,
    Participant,
    Scenario,
    Topic,
    fingerprint,
    new_id,
)


@dataclass(frozen=True)
class TopicTemplate:
    title: str
    intent: str
    decisions: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
    metrics: tuple[str, ...] = ()
    deadlines: tuple[str, ...] = ()
    retracted: tuple[str, ...] = ()


@dataclass(frozen=True)
class MeetingKind:
    kind_id: str
    label: str
    style_id: str
    roles: tuple[str, ...]
    nouns: tuple[str, ...]
    topics: tuple[TopicTemplate, ...]


FIRST_NAMES = (
    "Ada", "Rafael", "Priya", "Tomas", "Noor", "Wei", "Iris", "Dmitri",
    "Salma", "Kofi", "Hana", "Bram", "Lucia", "Owen", "Yuki", "Mateo",
    "Freya", "Ravi", "Elise", "Jonah", "Amara", "Sven", "Nadia", "Caleb",
)

FIRST_NAME_GENDER: dict[str, str] = {
    "Ada": "female",
    "Rafael": "male",
    "Priya": "female",
    "Tomas": "male",
    "Noor": "female",
    "Wei": "male",
    "Iris": "female",
    "Dmitri": "male",
    "Salma": "female",
    "Kofi": "male",
    "Hana": "female",
    "Bram": "male",
    "Lucia": "female",
    "Owen": "male",
    "Yuki": "female",
    "Mateo": "male",
    "Freya": "female",
    "Ravi": "male",
    "Elise": "female",
    "Jonah": "male",
    "Amara": "female",
    "Sven": "male",
    "Nadia": "female",
    "Caleb": "male",
}

LAST_INITIALS = tuple("BCDFGHKLMNPRSTVW")

SPEAKING_STYLES = (
    "concise and decisive",
    "rambling, thinks out loud",
    "asks a lot of clarifying questions",
    "skeptical, pushes back hard",
    "enthusiastic, jumps between ideas",
    "quiet, speaks rarely but precisely",
    "detail-obsessed, cites numbers",
)

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")

MONTH_DAYS = (
    "March 3rd", "March 17th", "April 2nd", "April 21st", "May 9th",
    "June 6th", "June 30th", "July 14th", "August 8th", "September 1st",
)


PRODUCT_KIND = MeetingKind(
    "product_review",
    "Product review",
    "business_meeting",
    ("product manager", "engineering lead", "designer", "data analyst", "support lead", "founder"),
    ("onboarding flow", "billing portal", "mobile app", "search page", "referral program", "admin console"),
    (
        TopicTemplate(
            "Quarterly targets",
            "Review whether the team will hit the quarter and what to cut if not.",
            decisions=(
                "The team will cut the {thing} refresh from this quarter and ship it next quarter instead.",
                "{owner} will own the quarterly target review from now on, replacing the ad-hoc process.",
                "Weekly target check-ins move from Friday to {weekday} so numbers are fresh.",
            ),
            actions=(
                "{owner} will rebuild the forecast model with the revised {thing} dates by {date}.",
                "{owner} will send the trimmed roadmap to the leadership channel before {date}.",
            ),
            risks=(
                "If the {thing} slips again the quarter target is unreachable and the team has no fallback.",
                "Only one engineer understands the forecast pipeline, so {owner} is a single point of failure.",
            ),
            questions=(
                "Nobody knew whether the {pct}% conversion drop is seasonal or caused by the {thing} change.",
                "It is still unclear who signs off on cutting scope once the quarter has started.",
            ),
            metrics=(
                "Conversion on the {thing} fell {pct}% month over month, from {n}% to {n2}%.",
                "The team is at {pct}% of the quarterly revenue target with {n} weeks left.",
            ),
            deadlines=("The revised forecast is due {date}.",),
            retracted=(
                "{owner} floated cancelling the {thing} entirely, then withdrew it once the revenue split was explained.",
                "A proposal to hire two contractors was raised and immediately rejected as unaffordable this quarter.",
            ),
        ),
        TopicTemplate(
            "Customer escalations",
            "Work through the open escalations and decide which ones get engineering time.",
            decisions=(
                "The {thing} outage postmortem will be published externally, not just internally.",
                "Escalations older than {n} days automatically page {owner} instead of waiting for triage.",
            ),
            actions=(
                "{owner} will write the postmortem draft and circulate it by {date}.",
                "{owner} will call the three largest affected accounts personally this week.",
            ),
            risks=(
                "Two enterprise accounts have hinted at churn if the {thing} is not stable by {date}.",
                "Support is absorbing the load manually and will not scale past {n} tickets a day.",
            ),
            questions=("Whether to offer service credits was raised but left for legal to answer.",),
            metrics=("Escalations are up to {n} open, against a normal baseline of {n2}.",),
            deadlines=("The postmortem must be public by {date}.",),
            retracted=(
                "Someone suggested pausing all feature work for a stability sprint; the group talked it down to a single week of bug fixing, which was itself left undecided.",
            ),
        ),
        TopicTemplate(
            "Pricing change",
            "Decide whether to raise prices and how to communicate it.",
            decisions=(
                "Prices go up {pct}% for new customers only; existing customers are grandfathered for {n} months.",
                "The pricing page rewrite will ship together with the change, not before it.",
            ),
            actions=(
                "{owner} will draft the customer email and get legal review by {date}.",
                "{owner} will model the churn impact at {pct}% and at double that rate.",
            ),
            risks=(
                "If the grandfather window leaks early, existing customers may pre-purchase and blow up the forecast.",
            ),
            questions=("Whether annual plans get the same treatment as monthly was not settled.",),
            metrics=("Current average revenue per account is ${n}0 per month.",),
            deadlines=("The announcement goes out {date}.",),
            retracted=(
                "A usage-based pricing model was sketched on the whiteboard and explicitly parked as out of scope for this cycle.",
            ),
        ),
        TopicTemplate(
            "Hiring plan",
            "Agree what roles to open and who runs the loops.",
            decisions=(
                "Two roles open now: one senior engineer for the {thing}, one support specialist.",
                "{owner} runs all hiring loops for the quarter to keep the bar consistent.",
            ),
            actions=(
                "{owner} will post both job descriptions by {date}.",
                "{owner} will assemble the interview panel and write the rubric.",
            ),
            risks=("Hiring at this level takes {n} weeks, so the roles will not help this quarter's targets.",),
            questions=("Whether the support role can be remote was left to the operations team.",),
            metrics=(),
            deadlines=("Job posts live by {date}.",),
            retracted=("Opening a third role for a data engineer was proposed and dropped for budget reasons.",),
        ),
        TopicTemplate(
            "Competitive response",
            "React to a competitor's launch without derailing the roadmap.",
            decisions=(
                "The team will not chase the competitor's feature; it will invest in {thing} depth instead.",
                "A one-page comparison sheet will be produced for the sales team.",
            ),
            actions=(
                "{owner} will interview {n} customers about whether the competing feature matters to them.",
                "{owner} will write the comparison sheet by {date}.",
            ),
            risks=("Sales is already discounting to hold deals, which erodes the pricing change discussed earlier.",),
            questions=("Nobody could say how many deals were actually lost to the competitor.",),
            metrics=("Sales reported {n} deals where the competitor was mentioned this month.",),
            deadlines=(),
            retracted=("Building a rushed clone of the competitor's feature in {n} weeks was floated and rejected.",),
        ),
        TopicTemplate(
            "Retention experiments",
            "Choose which retention experiments to run next.",
            decisions=(
                "Only two experiments run at once so results stay readable.",
                "The {thing} nudge experiment goes first because it is cheapest to build.",
            ),
            actions=(
                "{owner} will define the success metric and the stop rule before launch.",
                "{owner} will set up the dashboard by {date}.",
            ),
            risks=("Running experiments during the pricing change will confound both results.",),
            questions=("Whether to hold out a control group across the whole quarter was debated and left open.",),
            metrics=("Week-four retention sits at {pct}%, flat for three months.",),
            deadlines=("First experiment launches {date}.",),
            retracted=("A redesign of the entire {thing} was suggested as an experiment and ruled too large to measure.",),
        ),
    ),
)


TECHNICAL_KIND = MeetingKind(
    "architecture_review",
    "Architecture review",
    "technical_meeting",
    ("staff engineer", "backend engineer", "SRE", "platform lead", "security engineer", "tech lead"),
    ("ingest pipeline", "auth service", "job scheduler", "event bus", "caching layer", "migration tooling"),
    (
        TopicTemplate(
            "Datastore migration",
            "Pick a migration strategy and agree the rollback path.",
            decisions=(
                "The migration runs dual-write for {n} weeks before any read traffic moves.",
                "Rollback is a config flag, not a code deploy, so it can be flipped during an incident.",
                "The {thing} keeps its existing schema; only the storage engine changes.",
            ),
            actions=(
                "{owner} will write the dual-write adapter and land it behind a flag by {date}.",
                "{owner} will run a shadow load test at {n}x current traffic.",
            ),
            risks=(
                "Dual-write doubles write latency on the {thing}, which is already near its budget.",
                "There is no tested restore procedure for the new engine.",
            ),
            questions=(
                "Whether the backfill can run during business hours was not resolved.",
                "The team could not agree on how to verify parity between the two stores.",
            ),
            metrics=(
                "The {thing} currently handles {n},000 writes per second at p99 of {n2} milliseconds.",
                "Estimated backfill time is {n} hours for {n2} terabytes.",
            ),
            deadlines=("Dual-write must be live by {date} to leave room for the backfill.",),
            retracted=(
                "{owner} proposed skipping dual-write and doing a hard cutover during a maintenance window; the group rejected it after the restore gap came up.",
                "An idea to migrate the {thing} at the same time was floated and deferred.",
            ),
        ),
        TopicTemplate(
            "Incident review",
            "Understand last week's outage and prevent the repeat.",
            decisions=(
                "The retry storm is fixed with exponential backoff plus jitter, not by raising the rate limit.",
                "Every new service must ship with a load-shedding path before it takes production traffic.",
            ),
            actions=(
                "{owner} will add backoff to the {thing} client and deploy by {date}.",
                "{owner} will add a dashboard panel for queue depth and wire an alert at {n},000.",
            ),
            risks=("The same retry pattern exists in two other clients that nobody has audited.",),
            questions=("Why the alert did not fire for {n} minutes is still unexplained.",),
            metrics=(
                "The outage lasted {n} minutes and affected {pct}% of requests.",
                "Queue depth peaked at {n},000 messages against a normal ceiling of {n2}00.",
            ),
            deadlines=("Backoff fix deployed by {date}.",),
            retracted=("Raising the rate limit as a quick fix was suggested and explicitly rejected as papering over the cause.",),
        ),
        TopicTemplate(
            "API versioning",
            "Agree how breaking changes reach clients.",
            decisions=(
                "The API moves to date-based versions; clients pin a version header.",
                "Old versions are supported for {n} months after a successor ships, then removed.",
            ),
            actions=(
                "{owner} will write the versioning RFC and circulate it by {date}.",
                "{owner} will instrument which versions each client actually uses.",
            ),
            risks=("Two large integrations have no maintainer and will silently break at removal time.",),
            questions=("Whether internal callers follow the same deprecation clock was left open.",),
            metrics=("There are {n} distinct external integrations against the current API.",),
            deadlines=("RFC circulated by {date}.",),
            retracted=("Semantic versioning in the URL path was proposed and abandoned in favour of headers.",),
        ),
        TopicTemplate(
            "Build and CI health",
            "Cut the build time and stop the flaky tests.",
            decisions=(
                "Flaky tests get quarantined automatically after {n} failures rather than blocking merges.",
                "The {thing} test suite moves to a nightly job; only smoke tests run per commit.",
            ),
            actions=(
                "{owner} will add the quarantine tooling by {date}.",
                "{owner} will split the suite and measure the new per-commit time.",
            ),
            risks=("Quarantining without an owner means flaky tests are never actually fixed.",),
            questions=("Who reviews the quarantine list each week was not decided.",),
            metrics=("Median CI time is {n} minutes; the p95 is {n2} minutes.",),
            deadlines=(),
            retracted=("Buying larger CI runners was raised and set aside pending the split.",),
        ),
        TopicTemplate(
            "Security review",
            "Close the findings from the latest audit.",
            decisions=(
                "All {n} high findings are fixed before the release; mediums move to the next cycle.",
                "Secrets move out of environment variables into the managed store.",
            ),
            actions=(
                "{owner} will rotate the {thing} credentials and document the procedure by {date}.",
                "{owner} will add a CI check that fails on plaintext secrets.",
            ),
            risks=("Rotation touches every deploy target and has no dry-run mode.",),
            questions=("Whether the audit covers the {thing} at all was unclear to everyone present.",),
            metrics=("The audit produced {n} high and {n2} medium findings.",),
            deadlines=("Highs closed by {date}.",),
            retracted=("Delaying the release to fix mediums too was proposed and voted down.",),
        ),
        TopicTemplate(
            "Observability gaps",
            "Decide what to instrument before the next launch.",
            decisions=(
                "Tracing is enabled end to end on the {thing} path before launch, sampled at {pct}%.",
                "Logs move to structured JSON so they can be queried instead of grepped.",
            ),
            actions=(
                "{owner} will add trace propagation across the service boundary by {date}.",
                "{owner} will define the four dashboards that gate the launch.",
            ),
            risks=("Full-rate tracing would exceed the observability budget by roughly {pct}%.",),
            questions=("The retention period for traces was not agreed.",),
            metrics=("Current log volume is {n} gigabytes per day.",),
            deadlines=("Tracing live by {date}.",),
            retracted=("Switching vendors was floated and dropped as too disruptive before a launch.",),
        ),
    ),
)


ART_KIND = MeetingKind(
    "art_review",
    "Art review",
    "art_meeting",
    ("art director", "concept artist", "character artist", "environment artist", "producer", "creative director"),
    ("hero character", "market district", "boss arena", "key art", "vehicle set", "creature pass"),
    (
        TopicTemplate(
            "Colour direction",
            "Lock the palette for the next milestone.",
            decisions=(
                "The palette moves warmer for the {thing}: desaturated ochres against a cold sky.",
                "Neon accents are reserved for interactive objects only, nothing decorative.",
            ),
            actions=(
                "{owner} will repaint the {thing} key frame with the warmer palette by {date}.",
                "{owner} will produce a one-page palette sheet the whole team paints against.",
            ),
            risks=("The warmer palette fights the existing lighting rig and may need a relight of every scene.",),
            questions=("Whether the palette shift applies to the tutorial area was left open.",),
            metrics=(),
            deadlines=("Palette sheet by {date}.",),
            retracted=(
                "A fully monochrome treatment was pitched and rejected as unreadable in gameplay.",
            ),
        ),
        TopicTemplate(
            "Character silhouette pass",
            "Review the silhouettes and approve or reject each one.",
            decisions=(
                "Silhouette B is approved for the {thing}; A and C are cut.",
                "The shoulder line is exaggerated by roughly {pct}% so the character reads at distance.",
            ),
            actions=(
                "{owner} will take silhouette B to full colour by {date}.",
                "{owner} will test the silhouette at gameplay camera distance and report back.",
            ),
            risks=("The approved silhouette is expensive to rig and animation has not seen it yet.",),
            questions=("Whether the same treatment applies to the secondary cast was not decided.",),
            metrics=("The team reviewed {n} silhouettes in this pass.",),
            deadlines=("Colour pass due {date}.",),
            retracted=("Combining elements of A and B into a hybrid was suggested, tried on the spot, and abandoned.",),
        ),
        TopicTemplate(
            "Reference and mood",
            "Agree the visual references everyone is working from.",
            decisions=(
                "The reference board is narrowed to three sources; everything else is removed to stop drift.",
                "Photographic reference outranks illustrated reference when the two conflict.",
            ),
            actions=(
                "{owner} will clean up the board and post the link by {date}.",
                "{owner} will shoot lighting reference for the {thing} interior.",
            ),
            risks=("Half the team has been working from the old board for {n} weeks.",),
            questions=("Whether the film reference is licensable for marketing use is unanswered.",),
            metrics=(),
            deadlines=(),
            retracted=("Adding a fourth reference from a competing game was proposed and cut to avoid pastiche.",),
        ),
        TopicTemplate(
            "Asset review",
            "Walk the current assets and give feedback piece by piece.",
            decisions=(
                "The {thing} is approved with notes; the props set goes back for another pass.",
                "Texture density is standardised so nothing in a scene mismatches by more than one step.",
            ),
            actions=(
                "{owner} will address the notes on the {thing} and resubmit by {date}.",
                "{owner} will publish the texel density standard.",
            ),
            risks=("Reworking props a third time puts the milestone at risk.",),
            questions=("Whether the approved asset needs a damaged variant was raised and not answered.",),
            metrics=("{n} of {n2} assets in the set are now approved.",),
            deadlines=("Resubmission by {date}.",),
            retracted=("Outsourcing the props pass was floated and deferred until the standard exists.",),
        ),
        TopicTemplate(
            "Pipeline friction",
            "Fix what is slowing the artists down.",
            decisions=(
                "Export presets are versioned in the repository so nobody hand-configures them again.",
                "The nightly build produces an art-only package artists can open without engineering help.",
            ),
            actions=(
                "{owner} will commit the presets by {date}.",
                "{owner} will document the art-only build in the team wiki.",
            ),
            risks=("Artists are each losing about {n} hours a week to failed exports.",),
            questions=("Whether the tools engineer has capacity this milestone is unknown.",),
            metrics=("Export failures happen roughly {n} times a day across the team.",),
            deadlines=(),
            retracted=("Migrating to a different DCC tool was raised and dismissed as a milestone-killer.",),
        ),
    ),
)


DESIGN_KIND = MeetingKind(
    "design_critique",
    "Design critique",
    "design_meeting",
    ("product designer", "researcher", "content designer", "engineer", "design manager", "accessibility specialist"),
    ("checkout flow", "settings panel", "empty state", "notification centre", "onboarding tour", "search results"),
    (
        TopicTemplate(
            "Problem framing",
            "Agree what problem the redesign is actually solving.",
            decisions=(
                "The problem is framed as abandonment at the {thing}, not as visual dissatisfaction.",
                "Success is measured by completion rate, not by time on task.",
            ),
            actions=(
                "{owner} will rewrite the problem statement and share it by {date}.",
                "{owner} will pull the funnel numbers for the last {n} weeks.",
            ),
            risks=("The team has been designing against an unstated assumption for {n} weeks.",),
            questions=("Whether the abandonment is device-specific was raised and nobody had data.",),
            metrics=("Completion on the {thing} is {pct}%, against {n2}% on the legacy flow.",),
            deadlines=("Problem statement circulated by {date}.",),
            retracted=("Framing it as a performance problem was proposed and dropped when the load times came back clean.",),
        ),
        TopicTemplate(
            "Alternatives review",
            "Compare the concepts and pick what to prototype.",
            decisions=(
                "Concept two goes to prototype; concept one is kept as a fallback and concept three is cut.",
                "The prototype is clickable but not production-coded, to keep the loop under a week.",
            ),
            actions=(
                "{owner} will build the clickable prototype by {date}.",
                "{owner} will recruit {n} participants for the test.",
            ),
            risks=("Concept two depends on an API that does not exist yet.",),
            questions=("Whether the fallback is worth maintaining was not settled.",),
            metrics=(),
            deadlines=("Prototype ready {date}, testing the week after.",),
            retracted=("A fourth concept was sketched live and set aside as a later exploration.",),
        ),
        TopicTemplate(
            "Constraints and accessibility",
            "Surface the limits the design has to live inside.",
            decisions=(
                "The design targets AA contrast throughout; the brand accent is darkened to meet it.",
                "Every state in the {thing} must work with keyboard only.",
            ),
            actions=(
                "{owner} will update the tokens for the darkened accent by {date}.",
                "{owner} will run a screen-reader pass on the current build.",
            ),
            risks=("Marketing owns the brand accent and has not agreed to the change.",),
            questions=("Whether legacy screens are in scope for the contrast fix is undecided.",),
            metrics=("Contrast on the current accent measures {n}.{n2} to one.",),
            deadlines=("Token update by {date}.",),
            retracted=("An exemption for the marketing pages was requested and refused.",),
        ),
        TopicTemplate(
            "Research findings",
            "Review what testing showed and what to change.",
            decisions=(
                "The confirmation step stays; testing showed users rely on it.",
                "Terminology changes across the {thing} to match what participants actually said.",
            ),
            actions=(
                "{owner} will produce the revised copy by {date}.",
                "{owner} will write up the findings for the wider team.",
            ),
            risks=("The sample was {n} participants, all existing customers, so new-user behaviour is unknown.",),
            questions=("Whether to retest with new users before shipping was left open.",),
            metrics=("{n} of {n2} participants completed the task unaided.",),
            deadlines=("Findings written up by {date}.",),
            retracted=("Removing the confirmation step was the going-in assumption and was reversed by the findings.",),
        ),
        TopicTemplate(
            "Design system alignment",
            "Decide what belongs in the system versus this feature.",
            decisions=(
                "The new pattern is promoted into the system rather than living in the {thing}.",
                "One-off components need written sign-off from the system owner.",
            ),
            actions=(
                "{owner} will contribute the component with documentation by {date}.",
                "{owner} will audit the feature for other one-offs.",
            ),
            risks=("Promoting the pattern blocks the feature on system review, which has a {n}-week queue.",),
            questions=("Who maintains the pattern after handoff was not answered.",),
            metrics=(),
            deadlines=(),
            retracted=("Shipping the one-off now and promoting later was proposed and rejected on precedent grounds.",),
        ),
    ),
)


STANDUP_KIND = MeetingKind(
    "standup",
    "Stand-up",
    "standup_meeting",
    ("engineer", "engineer", "engineer", "tech lead", "QA engineer", "product manager"),
    ("importer", "settings screen", "billing job", "search index", "release branch", "test harness"),
    (
        TopicTemplate(
            "Round-robin updates",
            "Each person covers yesterday, today, and blockers.",
            decisions=(
                "The {thing} work is paused until the blocker on it clears.",
                "Pairing on the {thing} starts today rather than splitting it in two.",
            ),
            actions=(
                "{owner} will unblock the {thing} by getting access from the platform team today.",
                "{owner} will pick up the review queue so nothing waits more than a day.",
            ),
            risks=("Two people are blocked on the same missing access and nobody has escalated it.",),
            questions=("Whether the release branch cuts today or {weekday} was not confirmed.",),
            metrics=("{n} pull requests are open and waiting on review.",),
            deadlines=("Access request escalated by end of day.",),
            retracted=("Skipping stand-up for the rest of the week was suggested as a joke and dismissed.",),
        ),
        TopicTemplate(
            "Blockers",
            "Clear the things stopping work.",
            decisions=(
                "The flaky {thing} test is skipped for now with a ticket attached.",
                "{owner} takes over the deployment blocker from {owner2}.",
            ),
            actions=(
                "{owner} will file the ticket for the skipped test today.",
                "{owner} will chase the vendor about the expired certificate.",
            ),
            risks=("The certificate expires in {n} days and renewal takes longer than that.",),
            questions=("Whether the vendor contract is even current was unclear.",),
            metrics=(),
            deadlines=("Certificate renewed before {date}.",),
            retracted=("Rolling back the last deploy was floated and dropped once the cause was identified.",),
        ),
        TopicTemplate(
            "Release readiness",
            "Check whether the release is on track.",
            decisions=(
                "The release slips to {weekday} so the {thing} fix can be verified.",
                "Only blocking bugs go into the branch after the cut.",
            ),
            actions=(
                "{owner} will run the regression pass on the branch today.",
                "{owner} will update the release notes with the slipped date.",
            ),
            risks=("Slipping the release collides with the marketing announcement already scheduled.",),
            questions=("Whether marketing can move the announcement was not answered in the room.",),
            metrics=("{n} blocking bugs remain open, down from {n2} yesterday.",),
            deadlines=("Regression pass complete today; release {weekday}.",),
            retracted=("Shipping on time with the known bug was proposed and rejected.",),
        ),
        TopicTemplate(
            "Announcements",
            "Share things the whole team needs to hear.",
            decisions=("The team moves to the new on-call rotation starting {weekday}.",),
            actions=(
                "{owner} will publish the rotation schedule by {date}.",
                "{owner} will book the retrospective room for next week.",
            ),
            risks=("Two people are on holiday during the first week of the new rotation.",),
            questions=("Whether the rotation includes weekends was asked and deferred.",),
            metrics=(),
            deadlines=("Rotation published by {date}.",),
            retracted=("Adding a second daily sync was suggested and shot down.",),
        ),
    ),
)


CASUAL_KIND = MeetingKind(
    "team_sync",
    "Team sync",
    "meeting_summary",
    ("team lead", "operations manager", "marketer", "engineer", "customer success manager", "analyst"),
    ("launch plan", "help centre", "partner integration", "internal wiki", "budget sheet", "office move"),
    (
        TopicTemplate(
            "Launch planning",
            "Line up everything the launch needs.",
            decisions=(
                "Launch is {weekday}; the {thing} ships alongside it or not at all.",
                "The blog post and the in-app announcement go out together, not staggered.",
            ),
            actions=(
                "{owner} will finish the launch checklist by {date}.",
                "{owner} will brief the support team on the {n} most likely questions.",
            ),
            risks=("The partner has not confirmed their side and the launch depends on it.",),
            questions=("Whether to launch in all regions at once was raised and left to {owner}.",),
            metrics=("The waiting list is at {n},000 signups.",),
            deadlines=("Checklist complete by {date}, launch {weekday}.",),
            retracted=("A soft launch to {pct}% of users first was proposed and dropped for simplicity.",),
        ),
        TopicTemplate(
            "Budget review",
            "Go through spend and decide what to cut.",
            decisions=(
                "Tooling spend is capped; new tools need {owner}'s approval.",
                "The {thing} contract is renewed for one year, not three.",
            ),
            actions=(
                "{owner} will produce the line-by-line spend report by {date}.",
                "{owner} will negotiate the renewal down by at least {pct}%.",
            ),
            risks=("Three subscriptions renew automatically before the report is even ready.",),
            questions=("Whether the team owns the budget or finance does was genuinely unclear.",),
            metrics=("Monthly tooling spend is ${n},{n2}00.",),
            deadlines=("Report due {date}.",),
            retracted=("Cancelling the {thing} outright was suggested and reversed when its usage numbers came up.",),
        ),
        TopicTemplate(
            "Process changes",
            "Fix the parts of the way the team works that are not working.",
            decisions=(
                "Weekly written updates replace two of the three recurring meetings.",
                "The {thing} becomes the single source of truth; the shared drive is archived.",
            ),
            actions=(
                "{owner} will set up the written update template by {date}.",
                "{owner} will migrate the live documents and archive the rest.",
            ),
            risks=("Archiving the drive breaks links in customer-facing documentation.",),
            questions=("Who keeps the {thing} tidy over time was not decided.",),
            metrics=("The team is in meetings roughly {n} hours a week.",),
            deadlines=("Template ready by {date}.",),
            retracted=("Deleting the shared drive rather than archiving it was proposed and rejected.",),
        ),
        TopicTemplate(
            "Team health",
            "Talk about workload and morale.",
            decisions=(
                "On-call load is spread across {n} people instead of three.",
                "Friday afternoons are protected as focus time with no meetings.",
            ),
            actions=(
                "{owner} will redo the on-call schedule by {date}.",
                "{owner} will block the calendar for the whole team.",
            ),
            risks=("Two people have taken no leave this year and are visibly stretched.",),
            questions=("Whether focus time survives an incident week was raised and left open.",),
            metrics=(),
            deadlines=(),
            retracted=("A team offsite was floated and parked until the budget review lands.",),
        ),
    ),
)


MEETING_KINDS: tuple[MeetingKind, ...] = (
    CASUAL_KIND,
    PRODUCT_KIND,
    TECHNICAL_KIND,
    ART_KIND,
    DESIGN_KIND,
    STANDUP_KIND,
)

_KINDS_BY_ID = {kind.kind_id: kind for kind in MEETING_KINDS}

DEFAULT_KIND = CASUAL_KIND.kind_id


def kind_ids() -> tuple[str, ...]:
    return tuple(kind.kind_id for kind in MEETING_KINDS)


def get_kind(kind_id: str | None) -> MeetingKind:
    return _KINDS_BY_ID.get(str(kind_id or ""), CASUAL_KIND)


def suggested_style(kind_id: str | None) -> str:
    return get_kind(kind_id).style_id


def _participants(kind: MeetingKind, rng: random.Random, count: int) -> tuple[Participant, ...]:
    names = rng.sample(FIRST_NAMES, count)
    roles = list(kind.roles)
    rng.shuffle(roles)
    people: list[Participant] = []
    for index, name in enumerate(names):
        display = f"{name} {rng.choice(LAST_INITIALS)}."
        gender = FIRST_NAME_GENDER.get(name, "male" if index % 2 == 0 else "female")
        people.append(
            Participant(
                speaker_id=f"SPEAKER_{index:02d}",
                name=display,
                role=roles[index % len(roles)],
                gender=gender,  # type: ignore[arg-type]
                speaking_style=rng.choice(SPEAKING_STYLES),
                verbosity=round(rng.uniform(0.25, 1.0), 2),
            )
        )
    return tuple(people)


class _Filler:
    """Fills the `{owner}`-style slots in a template with seeded choices."""

    def __init__(self, kind: MeetingKind, people: tuple[Participant, ...], rng: random.Random) -> None:
        self.kind = kind
        self.people = people
        self.rng = rng

    def render(self, template: str) -> tuple[str, str]:
        """The filled sentence and the participant name used as its owner."""
        owner = self.rng.choice(self.people).name
        others = [person.name for person in self.people if person.name != owner]
        substitutions = {
            "owner": owner,
            "owner2": self.rng.choice(others) if others else owner,
            "thing": self.rng.choice(self.kind.nouns),
            "n": str(self.rng.randint(2, 48)),
            "n2": str(self.rng.randint(2, 96)),
            "pct": str(self.rng.randint(3, 65)),
            "date": self.rng.choice(MONTH_DAYS),
            "weekday": self.rng.choice(WEEKDAYS),
        }
        text = template
        for key, value in substitutions.items():
            text = text.replace("{" + key + "}", value)
        used_owner = owner if "{owner}" in template or "{owner2}" in template else ""
        return text, used_owner


def _pick(rng: random.Random, pool: tuple[str, ...], count: int) -> list[str]:
    if not pool or count <= 0:
        return []
    return rng.sample(list(pool), min(count, len(pool)))


def _salience(index: int) -> str:
    if index == 0:
        return "core"
    return "secondary" if index == 1 else "incidental"


def build_scenario(
    seed: int,
    *,
    kind_id: str | None = None,
    style_id: str | None = None,
    duration_minutes: int | None = None,
    disfluency: str = "light",
    mode: str = GROUNDED_MODE,
) -> Scenario:
    """A complete scenario derived from `seed`.

    Content is a pure function of the seed and the explicit arguments; only the
    scenario id and timestamp vary between calls.
    """
    rng = random.Random(seed)
    kind = get_kind(kind_id) if kind_id else rng.choice(MEETING_KINDS)
    style = str(style_id or kind.style_id)
    minutes = int(duration_minutes or rng.choice((15, 25, 30, 45, 60)))

    participant_count = max(2, min(len(FIRST_NAMES), 3 + minutes // 20 + rng.randint(0, 2)))
    people = _participants(kind, rng, participant_count)

    topic_count = max(2, min(len(kind.topics), 2 + minutes // 15))
    templates = rng.sample(list(kind.topics), topic_count)
    filler = _Filler(kind, people, rng)

    topics: list[Topic] = []
    facts: list[Fact] = []
    distractors: list[Distractor] = []

    for topic_index, template in enumerate(templates):
        topic_id = f"T{topic_index + 1}"
        topics.append(
            Topic(
                topic_id=topic_id,
                title=template.title,
                intent=template.intent,
                minutes=max(3, minutes // topic_count),
            )
        )

        planned: list[tuple[str, list[str]]] = [
            ("decision", _pick(rng, template.decisions, rng.randint(1, 2))),
            ("action_item", _pick(rng, template.actions, rng.randint(1, 2))),
            ("risk", _pick(rng, template.risks, rng.randint(0, 2))),
            ("open_question", _pick(rng, template.questions, rng.randint(0, 2))),
            ("metric", _pick(rng, template.metrics, rng.randint(0, 1))),
            ("deadline", _pick(rng, template.deadlines, rng.randint(0, 1))),
        ]
        for kind_name, chosen in planned:
            for position, raw in enumerate(chosen):
                text, owner = filler.render(raw)
                facts.append(
                    Fact(
                        fact_id=f"{topic_id}-{kind_name[:3].upper()}{position + 1}",
                        kind=kind_name,
                        text=text,
                        topic_id=topic_id,
                        owner=owner if kind_name in ("action_item", "decision") else "",
                        salience=_salience(position if kind_name in ("decision", "action_item") else position + 1),
                    )
                )

        for position, raw in enumerate(_pick(rng, template.retracted, rng.randint(0, 2))):
            text, _ = filler.render(raw)
            distractors.append(
                Distractor(
                    distractor_id=f"{topic_id}-D{position + 1}",
                    text=text,
                    topic_id=topic_id,
                    reason=rng.choice(("retracted", "rejected", "hypothetical")),
                )
            )

    title = f"{kind.label}: {topics[0].title}" if topics else kind.label

    return Scenario(
        scenario_id=new_id("scn"),
        seed=int(seed),
        mode=mode,
        style_id=style,
        meeting_kind=kind.kind_id,
        title=title,
        duration_minutes=minutes,
        disfluency=disfluency,
        participants=people,
        topics=tuple(topics),
        facts=tuple(facts),
        distractors=tuple(distractors),
    )


def build_freeform_scenario(
    seed: int,
    *,
    kind_id: str | None = None,
    style_id: str | None = None,
    duration_minutes: int | None = None,
    disfluency: str = "light",
) -> Scenario:
    """A scenario with participants and topic headings but no ground truth.

    The generator improvises the content, so nothing here can be graded for
    recall; these transcripts exist to exercise the reference-free rubric and to
    catch prompts that only look good on tidy synthetic material.
    """
    grounded = build_scenario(
        seed,
        kind_id=kind_id,
        style_id=style_id,
        duration_minutes=duration_minutes,
        disfluency=disfluency,
        mode=FREEFORM_MODE,
    )
    return Scenario(
        scenario_id=grounded.scenario_id,
        seed=grounded.seed,
        mode=FREEFORM_MODE,
        style_id=grounded.style_id,
        meeting_kind=grounded.meeting_kind,
        title=grounded.title,
        duration_minutes=grounded.duration_minutes,
        disfluency=grounded.disfluency,
        participants=grounded.participants,
        topics=grounded.topics,
        facts=(),
        distractors=(),
        created_at=grounded.created_at,
    )


def scenario_content_key(scenario: Scenario) -> str:
    """A fingerprint of a scenario's content, ignoring its id and timestamp."""
    payload = {
        "mode": scenario.mode,
        "kind": scenario.meeting_kind,
        "style": scenario.style_id,
        "minutes": str(scenario.duration_minutes),
        "people": "|".join(
            f"{p.speaker_id}:{p.name}:{p.role}:{p.gender}" for p in scenario.participants
        ),
        "topics": "|".join(f"{t.topic_id}:{t.title}" for t in scenario.topics),
        "facts": "|".join(f"{f.fact_id}:{f.kind}:{f.text}" for f in scenario.facts),
        "distractors": "|".join(f"{d.distractor_id}:{d.text}" for d in scenario.distractors),
    }
    return fingerprint(payload)
