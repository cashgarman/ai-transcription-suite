import { Reveal } from "@/components/reveal";
import { SectionHeading } from "@/components/section-heading";
import { FEATURES } from "@/lib/content";

const FORMATS = ["TXT", "MD", "JSON", "SRT", "VTT", "CSV", "PDF"];

export function Features()
{
  return (
    <section id="features" className="relative scroll-mt-24 border-y border-edge bg-sunken/40">
      <div className="page-pad mx-auto w-full max-w-6xl py-16 sm:py-24">
        <SectionHeading
          eyebrow="Features"
          title="A transcription workbench, not a text box"
          body="Summit is built for the recordings people actually have: long, overlapping, multi-speaker, and too sensitive to hand to a website."
        />

        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:mt-14 xl:grid-cols-4">
          {FEATURES.map((feature, index) => (
            <Reveal as="article" key={feature.title} delay={(index % 4) * 0.06}>
              <div className="group relative h-full overflow-hidden rounded-panel border border-edge bg-surface p-6 transition-all duration-300 hover:-translate-y-1 hover:border-accent/60 hover:bg-raised">
                <div
                  aria-hidden
                  className="absolute -right-10 -top-10 h-24 w-24 rounded-full bg-accent/0 blur-2xl transition-colors duration-500 group-hover:bg-accent/20"
                />
                <p className="relative font-mono text-[10px] uppercase tracking-[0.14em] text-accent">
                  {feature.meta}
                </p>
                <h3 className="relative mt-3 font-display text-lg font-semibold leading-snug text-ink">
                  {feature.title}
                </h3>
                <p className="relative mt-3 text-sm leading-relaxed text-muted">
                  {feature.body}
                </p>
              </div>
            </Reveal>
          ))}
        </div>

        <Reveal delay={0.15}>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-2.5 rounded-panel border border-edge bg-surface px-4 py-5 sm:px-6">
            <span className="mr-2 text-xs uppercase tracking-wider text-muted">
              Exports
            </span>
            {FORMATS.map((format) => (
              <span
                key={format}
                className="rounded-md border border-edge bg-sunken px-2.5 py-1 font-mono text-[11px] text-dim transition-colors hover:border-accent hover:text-accent"
              >
                {format}
              </span>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}
