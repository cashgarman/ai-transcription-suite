import { Reveal } from "@/components/reveal";
import { PIPELINE } from "@/lib/content";

export function PipelineStrip()
{
  return (
    <section className="border-y border-edge bg-sunken/60">
      <div className="page-pad mx-auto w-full max-w-6xl py-12 sm:py-14">
        <Reveal>
          <p className="text-center font-display text-xs font-semibold uppercase tracking-[0.22em] text-accent">
            One file in, five local stages, a finished document out
          </p>
        </Reveal>

        <ol className="mt-9 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {PIPELINE.map((stage, index) => (
            <Reveal as="li" key={stage.step} delay={index * 0.07}>
              <div className="group h-full rounded-panel border border-edge bg-surface p-4 transition-colors hover:border-accent/60">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[11px] text-accent">{stage.step}</span>
                  <span className="h-px flex-1 bg-edge transition-colors group-hover:bg-accent/40" />
                </div>
                <h3 className="mt-3 font-display text-sm font-semibold text-ink">
                  {stage.title}
                </h3>
                <p className="mt-1.5 text-xs leading-relaxed text-muted">{stage.body}</p>
              </div>
            </Reveal>
          ))}
        </ol>

        <Reveal delay={0.2}>
          <p className="mt-7 text-center text-xs text-muted">
            Models load one at a time and are unloaded between stages, so a mid-range
            card handles work that would otherwise need a workstation.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
