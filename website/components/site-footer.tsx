import Link from "next/link";
import { SummitMark, SummitWordmark } from "@/components/summit-mark";
import { SITE } from "@/lib/site";

const COLUMNS = [
  {
    heading: "Product",
    links: [
      { href: "/#features", label: "Features" },
      { href: "/#notes", label: "Notes styles" },
      { href: "/#pricing", label: "Pricing" },
      { href: "/download", label: "Download" },
    ],
  },
  {
    heading: "Details",
    links: [
      { href: "/privacy", label: "Privacy" },
      { href: "/#requirements", label: "Requirements" },
      { href: "/#faq", label: "FAQ" },
      { href: "/#waitlist", label: "Launch list" },
    ],
  },
];

export function SiteFooter()
{
  return (
    <footer className="border-t border-edge bg-sunken">
      <div className="page-pad mx-auto grid w-full max-w-6xl gap-10 py-14 md:grid-cols-[1.6fr_1fr_1fr]">
        <div>
          <div className="flex items-center gap-2.5">
            <SummitMark className="h-8 w-8" idPrefix="footer" />
            <SummitWordmark />
          </div>
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-muted">
            {SITE.tagline}
          </p>
          <p className="mt-4 text-xs text-muted">
            Windows 10/11 and Linux &middot; NVIDIA GPU with roughly 6&ndash;10 GB VRAM
            &middot; FFmpeg required
          </p>
        </div>

        {COLUMNS.map((column) => (
          <div key={column.heading}>
            <h2 className="font-display text-xs font-semibold uppercase tracking-[0.18em] text-accent">
              {column.heading}
            </h2>
            <ul className="mt-4 space-y-2.5">
              {column.links.map((link) => (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    className="text-sm text-dim transition-colors hover:text-accent"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="border-t border-edge/60">
        <div className="page-pad mx-auto flex w-full max-w-6xl flex-col gap-2 py-6 text-xs text-muted sm:flex-row sm:items-center sm:justify-between">
          <p>&copy; {new Date().getFullYear()} Summit. All processing happens on your machine.</p>
          <p>
            Diarization answers who spoke when. It is not voice identification.
          </p>
        </div>
      </div>
    </footer>
  );
}
