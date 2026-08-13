import { Reveal } from "@/components/reveal";
import { SectionHeading } from "@/components/section-heading";

const REQUIREMENTS = [
  { label: "Operating system", value: "Windows 10/11 or Linux" },
  { label: "GPU", value: "NVIDIA with a current driver" },
  { label: "VRAM", value: "6–10 GB depending on model" },
  { label: "Also needed", value: "FFmpeg and ffprobe on PATH" },
  { label: "Network", value: "First-run model download only" },
  { label: "Optional", value: "Ollama for AI-written notes" },
];

const VRAM = [
  { stage: "medium, INT8/mixed", peak: "2–4 GB", bar: 35 },
  { stage: "distil-large-v3, INT8/mixed", peak: "3–5 GB", bar: 48 },
  { stage: "large-v3, INT8/mixed", peak: "5–9 GB", bar: 82 },
  { stage: "WhisperX alignment", peak: "1–2 GB", bar: 18 },
  { stage: "pyannote diarization", peak: "2–4 GB", bar: 35 },
];

export function Requirements()
{
  return (
    <section
      id="requirements"
      className="scroll-mt-24 border-y border-edge bg-sunken/40"
    >
      <div className="page-pad mx-auto w-full max-w-6xl py-16 sm:py-24">
        <SectionHeading
          eyebrow="Requirements"
          title="Local means it runs on your hardware, so here are the numbers"
          body="No asterisks. If your machine cannot do this, we would rather you know before you download it than after."
        />

        <div className="mt-10 grid gap-6 md:grid-cols-[1fr_1.1fr] lg:mt-12">
          <Reveal>
            <dl className="grid gap-px overflow-hidden rounded-panel border border-edge bg-edge/60 sm:grid-cols-2">
              {REQUIREMENTS.map((item) => (
                <div key={item.label} className="bg-surface p-5">
                  <dt className="text-[10px] uppercase tracking-[0.16em] text-muted">
                    {item.label}
                  </dt>
                  <dd className="mt-1.5 text-sm text-ink">{item.value}</dd>
                </div>
              ))}
            </dl>
          </Reveal>

          <Reveal delay={0.1}>
            <div className="h-full rounded-panel border border-edge bg-surface p-6">
              <h3 className="font-display text-sm font-semibold text-ink">
                Expected peak VRAM
              </h3>
              <p className="mt-1 text-xs text-muted">
                Stages run sequentially, so these figures are not additive.
              </p>
              <ul className="mt-5 space-y-3.5">
                {VRAM.map((row) => (
                  <li key={row.stage}>
                    <div className="flex items-baseline justify-between text-xs">
                      <span className="text-dim">{row.stage}</span>
                      <span className="font-mono text-muted">{row.peak}</span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-sunken">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-accent-pressed to-accent"
                        style={{ width: `${row.bar}%` }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
              <p className="mt-5 border-t border-edge pt-4 text-xs leading-relaxed text-muted">
                Run out anyway and Summit halves the batch, steps down to a smaller
                model, then moves alignment or diarization to the CPU. It finishes the
                job and writes down what it changed.
              </p>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
