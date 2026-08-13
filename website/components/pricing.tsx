import Link from "next/link";
import { Reveal } from "@/components/reveal";
import { SectionHeading } from "@/components/section-heading";
import { PLANS } from "@/lib/pricing";

export function Pricing()
{
  return (
    <section id="pricing" className="page-pad mx-auto w-full max-w-6xl scroll-mt-24 py-16 sm:py-24">
      <SectionHeading
        align="center"
        eyebrow="Pricing"
        title="Try the whole thing on a ten-minute file"
        body="The trial is not a demo build. It is the shipping application with one restriction on length, so you can judge Summit on your own recordings, on your own hardware, before anyone asks you for money."
      />

      <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:mt-14 xl:grid-cols-4">
        {PLANS.map((plan, index) => (
          <Reveal as="article" key={plan.id} delay={index * 0.08}>
            <div
              className={`relative flex h-full flex-col rounded-panel border p-6 transition-all duration-300 hover:-translate-y-1 ${
                plan.featured
                  ? "border-accent bg-gradient-to-b from-accent/12 to-surface shadow-[0_0_60px_-24px_rgba(126,200,212,0.6)]"
                  : "border-edge bg-surface hover:border-accent/50"
              }`}
            >
              {plan.featured && (
                <span className="absolute -top-3 left-6 rounded-full border border-accent bg-window px-2.5 py-1 font-display text-[10px] font-semibold uppercase tracking-[0.16em] text-accent">
                  Start here
                </span>
              )}

              <h3 className="font-display text-sm font-semibold uppercase tracking-[0.16em] text-dim">
                {plan.name}
              </h3>
              <p className="mt-3 font-display text-3xl font-bold text-ink">{plan.price}</p>
              <p className="mt-1 text-xs text-muted">{plan.cadence}</p>
              <p className="mt-4 text-sm leading-relaxed text-dim">{plan.pitch}</p>

              <ul className="mt-5 flex-1 space-y-2.5">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex gap-2.5 text-sm text-muted">
                    <svg
                      viewBox="0 0 16 16"
                      className="mt-0.5 h-4 w-4 shrink-0 text-accent"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                    >
                      <path d="M3 8.5l3.2 3.2L13 5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>

              {plan.note && (
                <p className="mt-5 border-t border-edge pt-4 text-xs leading-relaxed text-muted">
                  {plan.note}
                </p>
              )}

              <Link
                href={plan.cta.href}
                className={`mt-6 inline-flex items-center justify-center rounded-lg px-4 py-2.5 text-sm font-semibold transition-colors ${
                  plan.featured
                    ? "border border-accent bg-accent text-sunken hover:border-accent-hover hover:bg-accent-hover"
                    : "border border-edge bg-raised text-ink hover:border-accent"
                }`}
              >
                {plan.cta.label}
              </Link>
            </div>
          </Reveal>
        ))}
      </div>

      <Reveal delay={0.2}>
        <p className="mt-8 text-center text-xs text-muted">
          Paid pricing is indicative while Summit finishes its first public release.
          Join the launch list and the price you are quoted will be the price you pay.
        </p>
      </Reveal>
    </section>
  );
}
