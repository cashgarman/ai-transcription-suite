type SummitMarkProps = {
  className?: string;
  framed?: boolean;
  animated?: boolean;
  /** Keeps gradient ids unique when several marks share a page. */
  idPrefix?: string;
};

/**
 * Web port of paint_summit_mark() in speaker_transcriber/ui/branding.py:
 * the same peak geometry, beacon, and radiating voice arcs.
 */
export function SummitMark({
  className,
  framed = true,
  animated = false,
  idPrefix = "summit",
}: SummitMarkProps)
{
  const peakGradient = `${idPrefix}-peak`;
  const frameGradient = `${idPrefix}-frame`;
  const glowGradient = `${idPrefix}-glow`;
  const beaconGradient = `${idPrefix}-beacon`;

  const arcs = [
    { d: "M 40.86 13.06 A 9 9 0 0 0 37.16 7.25", width: 2.4, opacity: 0.82 },
    { d: "M 44.80 12.36 A 13 13 0 0 0 39.46 3.97", width: 2.0, opacity: 0.66 },
    { d: "M 48.74 11.67 A 17 17 0 0 0 41.75 0.70", width: 1.6, opacity: 0.48 },
  ];

  return (
    <svg
      viewBox="0 0 64 64"
      className={className}
      role="img"
      aria-label="Summit"
      fill="none"
    >
      <defs>
        <linearGradient id={peakGradient} x1="32" y1="10" x2="32" y2="56.17" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#D7F4F8" />
          <stop offset="0.22" stopColor="#7EC8D4" />
          <stop offset="1" stopColor="#5FA8B4" />
        </linearGradient>
        <linearGradient id={frameGradient} x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#2A3940" />
          <stop offset="0.55" stopColor="#1B2429" />
          <stop offset="1" stopColor="#12181C" />
        </linearGradient>
        <radialGradient id={glowGradient} cx="32" cy="18" r="35" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#7EC8D4" stopOpacity="0.28" />
          <stop offset="1" stopColor="#7EC8D4" stopOpacity="0" />
        </radialGradient>
        <radialGradient id={beaconGradient} cx="32" cy="11.85" r="6" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#FFFFFF" stopOpacity="0.9" />
          <stop offset="0.45" stopColor="#95D5DF" stopOpacity="0.55" />
          <stop offset="1" stopColor="#95D5DF" stopOpacity="0" />
        </radialGradient>
      </defs>

      {framed && (
        <>
          <rect x="0.5" y="0.5" width="63" height="63" rx="14" fill={`url(#${frameGradient})`} />
          <rect x="0.5" y="0.5" width="63" height="63" rx="14" fill={`url(#${glowGradient})`} />
          <rect
            x="0.5"
            y="0.5"
            width="63"
            height="63"
            rx="14"
            stroke="#7EC8D4"
            strokeOpacity="0.19"
            strokeWidth="1"
          />
        </>
      )}

      <g stroke="#95D5DF" strokeLinecap="round">
        {arcs.map((arc, index) => (
          <path
            key={arc.d}
            d={arc.d}
            strokeWidth={arc.width}
            strokeOpacity={arc.opacity}
            className={animated ? "animate-beacon" : undefined}
            style={
              animated
                ? { animationDelay: `${index * 0.28}s`, transformOrigin: "32px 14.62px" }
                : undefined
            }
          />
        ))}
      </g>

      <path
        d="M 10.88 56.17 L 17.64 34.01 L 23.55 39.55 L 32 11.85 L 39.60 36.78 L 44.67 29.39 L 53.12 56.17 Z"
        fill={`url(#${peakGradient})`}
      />

      <circle
        cx="32"
        cy="11.85"
        r="6"
        fill={`url(#${beaconGradient})`}
        className={animated ? "animate-beacon" : undefined}
        style={animated ? { transformOrigin: "32px 11.85px" } : undefined}
      />
      <circle cx="32" cy="11.85" r="1.9" fill="#F4F7F8" />
    </svg>
  );
}

export function SummitWordmark({ className }: { className?: string })
{
  return (
    <span
      className={`font-display text-[1.05rem] font-bold uppercase tracking-[0.22em] text-ink ${className ?? ""}`}
    >
      Summit
    </span>
  );
}
