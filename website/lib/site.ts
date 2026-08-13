export const SITE = {
  name: "Summit",
  tagline:
    "Locally generated, completely private transcription and summarization of multi-speaker meetings.",
  description:
    "Summit transcribes audio and video, labels every speaker, and writes meeting notes entirely on your own computer. Nothing is uploaded.",
  trialMinutes: 10,
} as const;

/**
 * Both links fall back to the /download page, which explains the current
 * release state instead of dead-ending on a 404.
 */
export const DOWNLOAD_URL =
  process.env.NEXT_PUBLIC_DOWNLOAD_URL ?? "/download";

/** When unset, the waitlist form shows a confirmation without posting anywhere. */
export const WAITLIST_URL = process.env.NEXT_PUBLIC_WAITLIST_URL ?? "";

export const NAV_LINKS = [
  { href: "/#features", label: "Features" },
  { href: "/#notes", label: "Notes" },
  { href: "/#privacy", label: "Privacy" },
  { href: "/#pricing", label: "Pricing" },
] as const;
