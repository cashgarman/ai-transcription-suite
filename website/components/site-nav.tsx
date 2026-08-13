"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { SummitMark, SummitWordmark } from "@/components/summit-mark";
import { DOWNLOAD_URL, NAV_LINKS } from "@/lib/site";

export function SiteNav()
{
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() =>
  {
    const onScroll = () =>
    {
      setScrolled(window.scrollY > 12);
    };

    const onResize = () =>
    {
      if (window.innerWidth >= 1024)
      {
        setOpen(false);
      }
    };

    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onResize);
    return () =>
    {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  useEffect(() =>
  {
    document.body.style.overflow = open ? "hidden" : "";
    return () =>
    {
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <header
      className={`sticky top-0 z-50 border-b transition-colors duration-300 ${
        scrolled
          ? "border-edge bg-window/80 backdrop-blur-xl"
          : "border-transparent bg-transparent"
      }`}
    >
      <div className="page-pad mx-auto flex h-14 w-full max-w-6xl items-center gap-4 sm:h-16 sm:gap-6">
        <Link
          href="/"
          className="group flex items-center gap-2.5"
          onClick={() => setOpen(false)}
        >
          <SummitMark className="h-8 w-8" idPrefix="nav" animated />
          <SummitWordmark className="transition-colors group-hover:text-accent" />
        </Link>

        <nav className="ml-auto hidden items-center gap-1 lg:flex">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="rounded-lg px-3 py-2 text-sm text-dim transition-colors hover:bg-accent/10 hover:text-ink"
            >
              {link.label}
            </Link>
          ))}
          <Link
            href={DOWNLOAD_URL}
            className="ml-3 rounded-lg border border-accent bg-accent px-4 py-2 text-sm font-semibold text-sunken transition-colors hover:border-accent-hover hover:bg-accent-hover"
          >
            Free trial
          </Link>
        </nav>

        <button
          type="button"
          aria-label="Toggle navigation"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          className="ml-auto inline-flex h-11 w-11 items-center justify-center rounded-lg border border-edge text-dim transition-colors hover:border-accent hover:text-ink lg:hidden"
        >
          <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6">
            {open ? (
              <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
            ) : (
              <path d="M3 6h14M3 10h14M3 14h14" strokeLinecap="round" />
            )}
          </svg>
        </button>
      </div>

      {open && (
        <div className="border-t border-edge bg-window/95 backdrop-blur-xl lg:hidden">
          <nav className="page-pad mx-auto flex w-full max-w-6xl flex-col gap-1 py-4">
            {NAV_LINKS.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setOpen(false)}
                className="rounded-lg px-3 py-3 text-base text-dim transition-colors hover:bg-accent/10 hover:text-ink"
              >
                {link.label}
              </Link>
            ))}
            <Link
              href={DOWNLOAD_URL}
              onClick={() => setOpen(false)}
              className="mt-2 rounded-lg border border-accent bg-accent px-4 py-2.5 text-center text-sm font-semibold text-sunken"
            >
              Free trial
            </Link>
          </nav>
        </div>
      )}
    </header>
  );
}
