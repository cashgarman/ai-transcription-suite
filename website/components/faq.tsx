"use client";

import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { SectionHeading } from "@/components/section-heading";
import { FAQS } from "@/lib/content";

export function Faq()
{
  const [open, setOpen] = useState<number | null>(0);
  const reduced = useReducedMotion();

  return (
    <section id="faq" className="page-pad mx-auto w-full max-w-3xl scroll-mt-24 py-16 sm:py-24">
      <SectionHeading
        align="center"
        eyebrow="Questions"
        title="The things we would ask before installing this"
      />

      <div className="mt-12 divide-y divide-edge overflow-hidden rounded-panel border border-edge bg-surface">
        {FAQS.map((faq, index) =>
        {
          const expanded = open === index;

          return (
            <div key={faq.question}>
              <button
                type="button"
                aria-expanded={expanded}
                onClick={() => setOpen(expanded ? null : index)}
                className="flex min-h-12 w-full items-center gap-4 px-4 py-4 text-left transition-colors hover:bg-raised sm:px-6 sm:py-5"
              >
                <span
                  className={`flex-1 font-display text-base font-semibold transition-colors ${
                    expanded ? "text-accent" : "text-ink"
                  }`}
                >
                  {faq.question}
                </span>
                <svg
                  viewBox="0 0 16 16"
                  className={`h-4 w-4 shrink-0 text-accent transition-transform duration-300 ${
                    expanded ? "rotate-45" : ""
                  }`}
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                >
                  <path d="M8 3v10M3 8h10" strokeLinecap="round" />
                </svg>
              </button>

              <AnimatePresence initial={false}>
                {expanded && (
                  <motion.div
                    initial={reduced ? { opacity: 0 } : { height: 0, opacity: 0 }}
                    animate={reduced ? { opacity: 1 } : { height: "auto", opacity: 1 }}
                    exit={reduced ? { opacity: 0 } : { height: 0, opacity: 0 }}
                    transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
                    className="overflow-hidden"
                  >
                    <p className="px-4 pb-5 text-sm leading-relaxed text-muted sm:px-6 sm:pb-6">
                      {faq.answer}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
      </div>
    </section>
  );
}
