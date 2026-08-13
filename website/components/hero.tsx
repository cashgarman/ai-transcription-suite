"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { AppPreview } from "@/components/app-preview";
import { DOWNLOAD_URL, SITE } from "@/lib/site";

const BADGES = [
  "Windows 10/11 and Linux",
  "Runs on your NVIDIA GPU",
  "Offline after first setup",
];

export function Hero()
{
  const reduced = useReducedMotion();

  const rise = (delay: number) => ({
    initial: reduced ? { opacity: 0 } : { opacity: 0, y: 22 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.7, delay, ease: [0.22, 1, 0.36, 1] as const },
  });

  return (
    <section className="relative overflow-hidden">
      <BackdropMesh />

      <div className="page-pad relative mx-auto w-full max-w-6xl pb-14 pt-14 sm:pb-20 sm:pt-28">
        <motion.div {...rise(0)} className="flex justify-center">
          <span className="inline-flex max-w-full items-center gap-2 rounded-full border border-accent/30 bg-accent/10 px-3 py-1.5 text-center text-[11px] leading-tight text-accent sm:px-3.5 sm:text-xs">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-70" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-accent" />
            </span>
            Free trial &mdash; full features, {SITE.trialMinutes}-minute files
          </span>
        </motion.div>

        <motion.h1
          {...rise(0.08)}
          className="mx-auto mt-6 max-w-4xl text-balance-tight text-center font-display text-[2.05rem] font-bold leading-[1.08] tracking-tight text-ink sm:mt-7 sm:text-5xl lg:text-6xl"
        >
          Every voice. Every word.
          <span className="block bg-gradient-to-r from-accent-hover via-accent to-accent-pressed bg-clip-text text-transparent">
            Never the cloud.
          </span>
        </motion.h1>

        <motion.p
          {...rise(0.16)}
          className="mx-auto mt-6 max-w-2xl text-center text-base leading-relaxed text-dim sm:text-lg"
        >
          Summit transcribes your audio and video, labels who said what, and writes
          the meeting notes &mdash; entirely on your own computer. No upload, no
          account, no vendor holding your conversations.
        </motion.p>

        <motion.div
          {...rise(0.24)}
          className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row"
        >
          <Link
            href={DOWNLOAD_URL}
            className="group inline-flex w-full items-center justify-center gap-2 rounded-lg border border-accent bg-accent px-6 py-3 text-sm font-semibold text-sunken transition-all hover:border-accent-hover hover:bg-accent-hover hover:shadow-[0_0_36px_-6px_rgba(126,200,212,0.55)] sm:w-auto"
          >
            Start the free trial
            <svg viewBox="0 0 16 16" className="h-4 w-4 transition-transform group-hover:translate-y-0.5" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M8 2v9m0 0l3.5-3.5M8 11L4.5 7.5M2.5 13.5h11" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>
          <Link
            href="#preview"
            className="inline-flex w-full items-center justify-center rounded-lg border border-edge bg-raised px-6 py-3 text-sm font-medium text-ink transition-colors hover:border-accent sm:w-auto"
          >
            See Summit in action
          </Link>
        </motion.div>

        <motion.ul
          {...rise(0.32)}
          className="mt-7 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-xs text-muted"
        >
          {BADGES.map((badge) => (
            <li key={badge} className="flex items-center gap-1.5">
              <span className="h-1 w-1 rounded-full bg-accent" />
              {badge}
            </li>
          ))}
        </motion.ul>

        <motion.div
          id="preview"
          initial={reduced ? { opacity: 0 } : { opacity: 0, y: 40, scale: 0.985 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.9, delay: 0.4, ease: [0.22, 1, 0.36, 1] }}
          className="mt-16 scroll-mt-24"
        >
          <AppPreview />
          <p className="mt-4 text-center text-xs text-muted">
            A live illustration of the desktop pipeline. Every stage shown here runs
            on local hardware.
          </p>
        </motion.div>
      </div>
    </section>
  );
}

function BackdropMesh()
{
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute left-1/2 top-[-14rem] h-[34rem] w-[62rem] -translate-x-1/2 rounded-full bg-accent/12 blur-[130px] animate-drift" />
      <div
        className="absolute right-[-10rem] top-[16rem] h-[26rem] w-[26rem] rounded-full bg-accent-pressed/12 blur-[120px] animate-drift"
        style={{ animationDelay: "-8s" }}
      />
      <div
        className="absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgba(46,58,65,0.5) 1px, transparent 1px), linear-gradient(to bottom, rgba(46,58,65,0.5) 1px, transparent 1px)",
          backgroundSize: "72px 72px",
          maskImage:
            "radial-gradient(ellipse 70% 55% at 50% 25%, #000 30%, transparent 78%)",
          WebkitMaskImage:
            "radial-gradient(ellipse 70% 55% at 50% 25%, #000 30%, transparent 78%)",
        }}
      />
    </div>
  );
}
