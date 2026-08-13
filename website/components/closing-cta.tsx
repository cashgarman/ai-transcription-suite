import Link from "next/link";
import { Reveal } from "@/components/reveal";
import { SummitMark } from "@/components/summit-mark";
import { WaitlistForm } from "@/components/waitlist-form";
import { DOWNLOAD_URL, SITE } from "@/lib/site";

export function ClosingCta()
{
  return (
    <section
      id="waitlist"
      className="relative scroll-mt-24 overflow-hidden border-t border-edge"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-0 h-[30rem] w-[60rem] -translate-x-1/2 rounded-full bg-accent/12 blur-[130px] animate-drift"
      />

      <div className="page-pad relative mx-auto w-full max-w-3xl py-16 text-center sm:py-24">
        <Reveal>
          <SummitMark className="mx-auto h-16 w-16" idPrefix="cta" animated />
          <h2 className="mt-8 font-display text-3xl font-bold leading-tight text-ink sm:text-4xl">
            Put a real recording through it
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-base leading-relaxed text-dim">
            Take something you would never upload to a website &mdash; the difficult
            client call, the unreleased episode, the meeting with the lawyers &mdash;
            and give Summit {SITE.trialMinutes} minutes of it. That is the honest test,
            and it is the one the trial is built for.
          </p>
        </Reveal>

        <Reveal delay={0.1}>
          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              href={DOWNLOAD_URL}
              className="inline-flex w-full items-center justify-center rounded-lg border border-accent bg-accent px-6 py-3 text-sm font-semibold text-sunken transition-all hover:border-accent-hover hover:bg-accent-hover hover:shadow-[0_0_36px_-6px_rgba(126,200,212,0.55)] sm:w-auto"
            >
              Download for Windows
            </Link>
            <Link
              href="/#pricing"
              className="inline-flex w-full items-center justify-center rounded-lg border border-edge bg-raised px-6 py-3 text-sm font-medium text-ink transition-colors hover:border-accent sm:w-auto"
            >
              See pricing
            </Link>
          </div>
        </Reveal>

        <Reveal delay={0.18}>
          <div className="mt-14 rounded-panel border border-edge bg-surface p-7">
            <h3 className="font-display text-base font-semibold text-ink">
              Not ready to install anything?
            </h3>
            <p className="mx-auto mt-2 max-w-md text-sm text-muted">
              Leave an address and we will tell you when the full release, Linux
              packages, and pricing are final. One email, no drip campaign.
            </p>
            <div className="mt-5">
              <WaitlistForm />
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
