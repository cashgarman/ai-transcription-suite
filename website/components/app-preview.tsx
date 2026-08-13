"use client";

import { useEffect, useState } from "react";
import { useReducedMotion } from "motion/react";
import { SummitMark } from "@/components/summit-mark";

/** Same palette the desktop app assigns to diarized speakers. */
const SPEAKER_COLORS = ["#4FC3F7", "#FFB74D", "#81C784", "#BA68C8"] as const;

const SPEAKERS = [
  { label: "SPEAKER_00", name: "Dana Reyes", color: SPEAKER_COLORS[0] },
  { label: "SPEAKER_01", name: "Marcus Hale", color: SPEAKER_COLORS[1] },
  { label: "SPEAKER_02", name: "Priya Nair", color: SPEAKER_COLORS[2] },
  { label: "SPEAKER_03", name: "Tom Beckett", color: SPEAKER_COLORS[3] },
];

const TURNS = [
  {
    speaker: 0,
    time: "00:04:12",
    text: "Before we sign anything, I want to know where the recording physically lives.",
  },
  {
    speaker: 1,
    time: "00:04:19",
    text: "On this machine. It never gets uploaded, so there is no vendor to audit.",
  },
  {
    speaker: 2,
    time: "00:04:27",
    text: "That answers legal's question. Can we still hand them a signed summary?",
  },
  {
    speaker: 1,
    time: "00:04:33",
    text: "Yes — Summit exports the notes as a PDF with the action items attached.",
  },
  {
    speaker: 3,
    time: "00:04:41",
    text: "Then I'll take the follow-up. I'll have the draft circulated by Thursday.",
  },
];

const STAGES = [
  { label: "Converting audio with FFmpeg", start: 0, end: 0.09 },
  { label: "Transcribing with distil-large-v3", start: 0.09, end: 0.46 },
  { label: "Aligning word timestamps", start: 0.46, end: 0.62 },
  { label: "Detecting speaker turns", start: 0.62, end: 0.79 },
  { label: "Writing meeting notes locally", start: 0.79, end: 0.97 },
  { label: "Complete — 0 bytes uploaded", start: 0.97, end: 1 },
];

const NOTE_LINES = [
  { kind: "h", text: "Decisions" },
  { kind: "p", text: "Recordings stay on local hardware; no processor agreement required." },
  { kind: "h", text: "Action items" },
  { kind: "a", text: "Tom Beckett — circulate the signed summary by Thursday." },
  { kind: "a", text: "Priya Nair — confirm the retention wording with legal." },
];

const CYCLE_MS = 15000;
const TICK_MS = 60;

function stageFor(progress: number)
{
  return STAGES.find((stage) => progress < stage.end) ?? STAGES[STAGES.length - 1];
}

export function AppPreview()
{
  const reduced = useReducedMotion();
  // Starts at zero on both server and client; the effect below decides where
  // it goes, so the first paint always matches the server-rendered markup.
  const [progress, setProgress] = useState(0);

  useEffect(() =>
  {
    if (reduced)
    {
      const settle = window.setTimeout(() => setProgress(1), 0);
      return () => window.clearTimeout(settle);
    }

    const started = performance.now();
    const timer = window.setInterval(() =>
    {
      const elapsed = (performance.now() - started) % (CYCLE_MS + 2500);
      setProgress(Math.min(elapsed / CYCLE_MS, 1));
    }, TICK_MS);

    return () => window.clearInterval(timer);
  }, [reduced]);

  const stage = stageFor(progress);
  const stageIndex = STAGES.indexOf(stage);
  const percent = Math.round(progress * 100);
  const diarized = progress > 0.72;
  const turnsVisible = Math.min(
    TURNS.length,
    Math.floor(((progress - 0.09) / 0.37) * TURNS.length) + 1,
  );
  const notesVisible = Math.max(
    0,
    Math.min(NOTE_LINES.length, Math.floor(((progress - 0.79) / 0.18) * NOTE_LINES.length)),
  );

  return (
    <div className="overflow-hidden rounded-xl border border-edge bg-window shadow-[0_40px_90px_-30px_rgba(0,0,0,0.9)]">
      <div className="flex items-center gap-3 border-b border-edge bg-surface px-4 py-2.5">
        <SummitMark className="h-5 w-5" idPrefix="preview" framed={false} />
        <span className="font-display text-xs font-semibold uppercase tracking-[0.18em] text-dim">
          Summit
        </span>
        <span className="hidden min-w-0 truncate text-xs text-muted sm:inline">
          quarterly-review-2026-08.mp4
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-edge" />
          <span className="h-2.5 w-2.5 rounded-full bg-edge" />
          <span className="h-2.5 w-2.5 rounded-full bg-edge" />
        </div>
      </div>

      <div className="grid min-w-0 grid-cols-1 gap-px bg-edge/60 md:grid-cols-[minmax(0,1fr)_minmax(11rem,14rem)] lg:grid-cols-[10.5rem_minmax(0,1fr)_12.5rem]">
        <aside className="hidden bg-window p-4 lg:block">
          <SidebarField label="Model" value="distil-large-v3" />
          <SidebarField label="Language" value="auto" />
          <SidebarField label="Speakers" value="Minimum / maximum" />
          <SidebarField label="Compute" value="int8_float16" />
          <div className="mt-4 rounded-lg border border-accent bg-accent px-3 py-2 text-center text-xs font-semibold text-sunken">
            {progress >= 1 ? "Start" : "Cancel"}
          </div>
          <div className="mt-4 space-y-2.5">
            <Meter label="VRAM" value={progress > 0.05 && progress < 0.98 ? 62 : 4} />
            <Meter label="GPU" value={progress > 0.05 && progress < 0.98 ? 88 : 2} />
          </div>
        </aside>

        <div className="min-w-0 bg-window">
          <div className="flex gap-1 border-b border-edge px-3 pt-3">
            <Tab active>Transcript</Tab>
            <Tab>Speakers</Tab>
            <Tab>Notes</Tab>
          </div>

          <div className="min-h-[260px] space-y-3 p-4">
            {TURNS.map((turn, index) =>
            {
              const speaker = SPEAKERS[turn.speaker];
              const visible = index < turnsVisible;
              const isLast = index === turnsVisible - 1;

              return (
                <div
                  key={turn.time}
                  className="transition-all duration-500"
                  style={{
                    opacity: visible ? 1 : 0,
                    transform: visible ? "translateY(0)" : "translateY(8px)",
                  }}
                >
                  <div className="flex items-baseline gap-2">
                    <span
                      className="font-display text-[11px] font-semibold uppercase tracking-wider transition-colors duration-700"
                      style={{ color: diarized ? speaker.color : "#9AA7AE" }}
                    >
                      {diarized ? speaker.name : speaker.label}
                    </span>
                    <span className="font-mono text-[10px] text-muted">{turn.time}</span>
                  </div>
                  <p className="mt-1 text-[13px] leading-relaxed text-dim">
                    {turn.text}
                    {isLast && progress < 0.46 && (
                      <span className="ml-0.5 inline-block h-3.5 w-[2px] translate-y-0.5 bg-accent animate-caret" />
                    )}
                  </p>
                </div>
              );
            })}
          </div>
        </div>

        <aside className="min-w-0 border-t border-edge bg-window p-4 md:border-t-0">
          <p className="font-display text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">
            Meeting notes
          </p>
          <div className="mt-3 space-y-2.5">
            {NOTE_LINES.map((line, index) => (
              <div
                key={line.text}
                className="transition-all duration-500"
                style={{
                  opacity: index < notesVisible ? 1 : 0.12,
                  transform: index < notesVisible ? "translateY(0)" : "translateY(6px)",
                }}
              >
                {line.kind === "h" ? (
                  <p className="font-display text-[11px] font-semibold uppercase tracking-wider text-dim">
                    {line.text}
                  </p>
                ) : (
                  <p className="flex gap-1.5 text-[11px] leading-relaxed text-muted">
                    <span className="text-accent">{line.kind === "a" ? "▸" : "—"}</span>
                    <span>{line.text}</span>
                  </p>
                )}
              </div>
            ))}
          </div>
        </aside>
      </div>

      <div className="border-t border-edge bg-surface px-4 py-3">
        <div className="flex items-center justify-between text-[11px]">
          <span className="min-w-0 truncate pr-3 text-dim">{stage.label}</span>
          <span className="font-mono text-muted">{percent}%</span>
        </div>
        <div className="mt-2 h-2.5 overflow-hidden rounded-full border border-edge bg-sunken">
          <div
            className={`h-full rounded-full ${
              progress >= 1 ? "bg-success" : "hazard-stripes animate-stripes"
            }`}
            style={{ width: `${Math.max(percent, 2)}%`, transition: "width 120ms linear" }}
          />
        </div>
        <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted">
          {STAGES.slice(0, 5).map((item, index) => (
            <span
              key={item.label}
              className={index <= stageIndex ? "text-accent" : undefined}
            >
              {index < stageIndex ? "✓ " : ""}
              {item.label.split(" ").slice(0, 2).join(" ")}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function SidebarField({ label, value }: { label: string; value: string })
{
  return (
    <div className="mb-2.5">
      <p className="text-[10px] uppercase tracking-wider text-muted">{label}</p>
      <div className="mt-1 truncate rounded-lg border border-edge bg-sunken px-2.5 py-1.5 text-[11px] text-dim">
        {value}
      </div>
    </div>
  );
}

function Meter({ label, value }: { label: string; value: number })
{
  return (
    <div>
      <div className="flex justify-between text-[10px] text-muted">
        <span>{label}</span>
        <span className="font-mono">{value}%</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full border border-edge bg-sunken">
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-700"
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

function Tab({ children, active }: { children: string; active?: boolean })
{
  return (
    <span
      className={`rounded-t-lg border border-b-0 px-3 py-1.5 text-[11px] ${
        active
          ? "border-edge bg-surface text-ink"
          : "border-transparent text-muted"
      }`}
    >
      {children}
    </span>
  );
}
