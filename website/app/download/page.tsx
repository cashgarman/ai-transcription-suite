import type { Metadata } from "next";
import Link from "next/link";
import { Reveal } from "@/components/reveal";
import { SummitMark } from "@/components/summit-mark";
import { WaitlistForm } from "@/components/waitlist-form";
import { SITE } from "@/lib/site";

export const metadata: Metadata = {
  title: "Download the free trial",
  description:
    "Download Summit and transcribe up to ten minutes of any audio or video file with every feature unlocked.",
};

const INSTALLER_URL = process.env.NEXT_PUBLIC_WINDOWS_INSTALLER_URL ?? "";

const SETUP_STEPS = [
  {
    title: "Install FFmpeg",
    body: "Summit uses it to decode media. Both ffmpeg and ffprobe need to be on your PATH.",
  },
  {
    title: "Check your GPU driver",
    body: "Run nvidia-smi. If it reports your card, you are ready for CUDA inference.",
  },
  {
    title: "Add a Hugging Face token",
    body: "Free, read-only, and used once to fetch the gated speaker model. Paste it into Settings; it goes to your credential store.",
  },
  {
    title: "Optional: install Ollama",
    body: "Only needed for AI-written meeting notes. Transcription works fully without it.",
  },
];

export default function DownloadPage()
{
  return (
    <div className="relative overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-[-16rem] h-[32rem] w-[52rem] -translate-x-1/2 rounded-full bg-accent/12 blur-[130px] animate-drift"
      />

      <div className="page-pad relative mx-auto w-full max-w-3xl py-16 sm:py-28">
        <Reveal className="text-center">
          <SummitMark className="mx-auto h-16 w-16" idPrefix="download" animated />
          <h1 className="mt-8 font-display text-4xl font-bold leading-tight text-ink sm:text-5xl">
            Download the free trial
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-base leading-relaxed text-dim">
            The complete application. Every model, every export format, every notes
            style. Each audio or video file is transcribed up to{" "}
            {SITE.trialMinutes} minutes.
          </p>
        </Reveal>

        <Reveal delay={0.1}>
          <div className="mt-10 rounded-panel border border-accent/40 bg-gradient-to-b from-accent/10 to-surface p-7 text-center">
            {INSTALLER_URL ? (
              <>
                <a
                  href={INSTALLER_URL}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-accent bg-accent px-7 py-3.5 text-sm font-semibold text-sunken transition-colors hover:border-accent-hover hover:bg-accent-hover"
                >
                  Download for Windows
                </a>
                <p className="mt-3 text-xs text-muted">
                  Windows 10/11, 64-bit. Linux instructions are in the repository.
                </p>
              </>
            ) : (
              <>
                <p className="font-display text-lg font-semibold text-ink">
                  The Windows installer is being packaged
                </p>
                <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted">
                  Summit currently ships as a one-folder build from source, and the
                  signed installer is next on the list. Leave an address and you will
                  get the download link the day it exists.
                </p>
                <div className="mt-6">
                  <WaitlistForm />
                </div>
              </>
            )}
          </div>
        </Reveal>

        <Reveal delay={0.16}>
          <h2 className="mt-16 font-display text-xl font-bold text-ink">
            What to have ready
          </h2>
          <ol className="mt-6 space-y-3">
            {SETUP_STEPS.map((step, index) => (
              <li
                key={step.title}
                className="flex gap-4 rounded-panel border border-edge bg-surface p-5"
              >
                <span className="font-mono text-xs text-accent">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <p className="font-display text-sm font-semibold text-ink">
                    {step.title}
                  </p>
                  <p className="mt-1 text-sm leading-relaxed text-muted">{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </Reveal>

        <Reveal delay={0.22}>
          <p className="mt-10 text-center text-sm text-muted">
            Unsure whether your machine can run it?{" "}
            <Link
              href="/#requirements"
              className="text-accent transition-colors hover:text-accent-hover"
            >
              Check the requirements
            </Link>{" "}
            first.
          </p>
        </Reveal>
      </div>
    </div>
  );
}
