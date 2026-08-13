"use client";

import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { SectionHeading } from "@/components/section-heading";
import { NOTE_STYLES } from "@/lib/content";

const SAMPLES: Record<string, string[]> = {
  "Meeting Summary": [
    "# Quarterly Review — 12 August",
    "",
    "## Executive summary",
    "The team agreed to keep all recordings on local hardware and to",
    "circulate a signed summary to legal by Thursday.",
    "",
    "## Decisions",
    "- Recordings remain on local hardware; no processor agreement needed.",
    "",
    "## Action items",
    "- Tom Beckett — circulate the signed summary by Thursday.",
    "- Priya Nair — confirm retention wording with legal.",
  ],
  "Technical Meeting": [
    "# Decision record — transcript storage",
    "",
    "## Problem",
    "Recordings contain privileged client audio that cannot leave the network.",
    "",
    "## Options considered",
    "1. Hosted transcription API — rejected, adds a subprocessor.",
    "2. Local GPU pipeline — accepted.",
    "",
    "## Decision",
    "Run transcription and diarization locally on the review workstation.",
    "",
    "## Consequences",
    "Requires an NVIDIA card per reviewer; removes the vendor audit entirely.",
  ],
  "Stand-Up Meeting": [
    "# Stand-up — Tuesday",
    "",
    "## Dana Reyes",
    "- Yesterday: finished the retention policy draft.",
    "- Today: review the export templates.",
    "- Blockers: none.",
    "",
    "## Marcus Hale",
    "- Yesterday: benchmarked the diarization stage.",
    "- Today: cut VRAM use on the alignment pass.",
    "- Blockers: waiting on a driver update.",
  ],
  "AI Voiced Dialogue": [
    "HOST A: So they recorded the whole quarterly review and never uploaded it?",
    "HOST B: Not a byte. The transcription ran on the machine in the room.",
    "HOST A: And the notes?",
    "HOST B: Same machine. A local model wrote them while the transcript",
    "         was still on screen.",
    "HOST A: That is going to make the legal team very quiet, in a good way.",
  ],
};

const SAMPLE_KEYS = Object.keys(SAMPLES);

export function NoteStyles()
{
  const [active, setActive] = useState(SAMPLE_KEYS[0]);
  const reduced = useReducedMotion();

  return (
    <section id="notes" className="page-pad mx-auto w-full max-w-6xl scroll-mt-24 py-16 sm:py-24">
      <SectionHeading
        eyebrow="Meeting notes"
        title="It writes the document you were going to write anyway"
        body="Connect a local Ollama model and Summit turns the transcript into a finished piece of writing. Twelve styles, each with its own prompt pack, so a board summary does not read like a stand-up."
      />

      <div className="mt-10 grid gap-8 lg:mt-12 lg:grid-cols-[1fr_1.15fr]">
        <div>
          <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
            {NOTE_STYLES.map((style) =>
            {
              const selectable = SAMPLE_KEYS.includes(style.name);
              const isActive = selectable && active === style.name;

              return (
                <button
                  key={style.name}
                  type="button"
                  disabled={!selectable}
                  onClick={() => setActive(style.name)}
                  className={`rounded-panel border p-3.5 text-left transition-all ${
                    isActive
                      ? "border-accent bg-accent/10"
                      : "border-edge bg-surface"
                  } ${
                    selectable
                      ? "cursor-pointer hover:border-accent/70 hover:bg-raised"
                      : "cursor-default opacity-80"
                  }`}
                >
                  <p
                    className={`font-display text-sm font-semibold ${
                      isActive ? "text-accent" : "text-ink"
                    }`}
                  >
                    {style.name}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-muted">{style.body}</p>
                </button>
              );
            })}
          </div>
          <p className="mt-4 text-xs text-muted">
            Four styles are previewed here. All twelve ship with the trial.
          </p>
        </div>

        <div className="lg:sticky lg:top-24 lg:h-fit">
          <div className="overflow-hidden rounded-panel border border-edge bg-sunken">
            <div className="flex items-center gap-2 border-b border-edge bg-surface px-4 py-2.5">
              <span className="h-2 w-2 rounded-full bg-accent" />
              <span className="font-mono text-[11px] text-dim">
                {active.toLowerCase().replace(/\s+/g, "-")}.md
              </span>
              <span className="ml-auto text-[10px] uppercase tracking-wider text-muted">
                Generated locally
              </span>
            </div>
            <div className="min-h-[340px] p-5">
              <AnimatePresence mode="wait">
                <motion.pre
                  key={active}
                  initial={reduced ? { opacity: 0 } : { opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.32 }}
                  className="whitespace-pre-wrap font-mono text-[12px] leading-relaxed text-dim"
                >
                  {SAMPLES[active].map((line, index) => (
                    <motion.span
                      key={`${active}-${index}`}
                      initial={reduced ? false : { opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: reduced ? 0 : 0.05 + index * 0.035 }}
                      className={`block ${
                        line.startsWith("#") ? "font-semibold text-accent" : ""
                      } ${line.startsWith("HOST") ? "text-ink" : ""}`}
                    >
                      {line || "\u00a0"}
                    </motion.span>
                  ))}
                </motion.pre>
              </AnimatePresence>
            </div>
          </div>
          <p className="mt-3 text-xs text-muted">
            Notes are drafted by an Ollama model on your machine. If the GPU runs
            short, Summit offers a smaller context or model rather than losing the
            text already written.
          </p>
        </div>
      </div>
    </section>
  );
}
