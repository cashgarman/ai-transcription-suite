"use client";

import { useState, type FormEvent } from "react";
import { WAITLIST_URL } from "@/lib/site";

type Status = "idle" | "sending" | "done" | "error";

export function WaitlistForm({ compact = false }: { compact?: boolean })
{
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<Status>("idle");

  async function onSubmit(event: FormEvent<HTMLFormElement>)
  {
    event.preventDefault();

    if (status === "sending")
    {
      return;
    }

    if (!WAITLIST_URL)
    {
      setStatus("done");
      return;
    }

    setStatus("sending");

    try
    {
      const response = await fetch(WAITLIST_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ email }),
      });

      setStatus(response.ok ? "done" : "error");
    }
    catch
    {
      setStatus("error");
    }
  }

  if (status === "done")
  {
    return (
      <div
        className={`rounded-panel border border-success/40 bg-success/10 px-5 py-4 text-sm text-dim ${
          compact ? "" : "mx-auto max-w-md"
        }`}
      >
        <p className="font-semibold text-success">You are on the list.</p>
        <p className="mt-1 text-muted">
          We will email you once about the release, and never sell the address.
        </p>
      </div>
    );
  }

  return (
    <form
      onSubmit={onSubmit}
      className={compact ? "" : "mx-auto w-full max-w-md"}
    >
      <div className="flex flex-col gap-3 sm:flex-row">
        <label className="sr-only" htmlFor="waitlist-email">
          Email address
        </label>
        <input
          id="waitlist-email"
          type="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@company.com"
          className="min-w-0 flex-1 rounded-lg border border-edge bg-sunken px-4 py-3 text-sm text-ink outline-none transition-colors placeholder:text-muted focus:border-accent"
        />
        <button
          type="submit"
          disabled={status === "sending"}
          className="rounded-lg border border-accent bg-accent px-5 py-3 text-sm font-semibold text-sunken transition-colors hover:border-accent-hover hover:bg-accent-hover disabled:opacity-60"
        >
          {status === "sending" ? "Sending…" : "Notify me"}
        </button>
      </div>

      {status === "error" && (
        <p className="mt-2 text-xs text-danger">
          That did not go through. Try again in a moment.
        </p>
      )}
    </form>
  );
}
