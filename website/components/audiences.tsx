import { Reveal } from "@/components/reveal";
import { SectionHeading } from "@/components/section-heading";
import { AUDIENCES } from "@/lib/content";

export function Audiences()
{
  return (
    <section id="audiences" className="page-pad mx-auto w-full max-w-6xl py-16 sm:py-24">
      <SectionHeading
        align="center"
        eyebrow="Who it is for"
        title="Two very different users, one uncomfortable question"
        body="Whether you answer to a compliance officer or only to yourself, the question is the same: who else gets to hear this? With Summit, nobody does."
      />

      <div className="mt-10 grid gap-6 md:grid-cols-2 lg:mt-14">
        {AUDIENCES.map((audience, index) => (
          <Reveal as="article" key={audience.eyebrow} delay={index * 0.1}>
            <div className="relative h-full overflow-hidden rounded-panel border border-edge bg-surface p-5 transition-colors hover:border-accent/50 sm:p-8">
              <div
                aria-hidden
                className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/60 to-transparent"
              />
              <p className="font-display text-xs font-semibold uppercase tracking-[0.2em] text-accent">
                {audience.eyebrow}
              </p>
              <h3 className="mt-3 font-display text-2xl font-bold leading-tight text-ink">
                {audience.title}
              </h3>
              <p className="mt-4 text-sm leading-relaxed text-dim">{audience.body}</p>
              <ul className="mt-6 space-y-3">
                {audience.points.map((point) => (
                  <li key={point} className="flex gap-3 text-sm text-muted">
                    <svg
                      viewBox="0 0 16 16"
                      className="mt-0.5 h-4 w-4 shrink-0 text-accent"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                    >
                      <path d="M3 8.5l3.2 3.2L13 5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
