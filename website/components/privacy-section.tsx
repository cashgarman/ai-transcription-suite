import Link from "next/link";
import { Reveal } from "@/components/reveal";
import { SectionHeading } from "@/components/section-heading";
import { PRIVACY_POINTS } from "@/lib/content";

export function PrivacySection()
{
  return (
    <section
      id="privacy"
      className="relative scroll-mt-24 overflow-hidden border-y border-edge bg-sunken/60"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-1/2 h-[28rem] w-[52rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent/8 blur-[140px]"
      />

      <div className="page-pad relative mx-auto w-full max-w-6xl py-16 sm:py-24">
        <SectionHeading
          align="center"
          eyebrow="Privacy"
          title="The strongest privacy policy is not having a server"
          body="Summit has no account system, no telemetry pipeline, and nowhere to send your audio even if it wanted to. Your recording is opened by a program on your desk and it stays there."
        />

        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:mt-14 lg:grid-cols-4">
          {PRIVACY_POINTS.map((point, index) => (
            <Reveal key={point.title} delay={index * 0.07}>
              <div className="h-full rounded-panel border border-edge bg-surface p-6">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-accent/40 bg-accent/10">
                  <svg
                    viewBox="0 0 20 20"
                    className="h-4.5 w-4.5 text-accent"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.6"
                  >
                    <path
                      d="M10 2.5l6 2.5v5c0 3.6-2.5 6.6-6 7.5-3.5-.9-6-3.9-6-7.5V5l6-2.5z"
                      strokeLinejoin="round"
                    />
                    <path d="M7.2 10l2 2 3.6-3.8" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <h3 className="mt-4 font-display text-base font-semibold text-ink">
                  {point.title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">{point.body}</p>
              </div>
            </Reveal>
          ))}
        </div>

        <Reveal delay={0.2}>
          <div className="mt-8 rounded-panel border border-accent/30 bg-accent/5 px-4 py-5 text-center sm:px-6 sm:py-6">
            <p className="text-sm leading-relaxed text-dim">
              Rotating local logs record models, stage durations, and fallback
              decisions so you can audit a run &mdash; and your Hugging Face token is
              stored in the operating system credential store, kept out of the
              settings file, and redacted from those logs.
            </p>
            <Link
              href="/privacy"
              className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-accent transition-colors hover:text-accent-hover"
            >
              Read exactly what touches the network
              <span aria-hidden>&rarr;</span>
            </Link>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
