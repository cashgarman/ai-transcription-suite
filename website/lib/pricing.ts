export type Plan = {
  id: string;
  name: string;
  price: string;
  cadence: string;
  pitch: string;
  features: string[];
  cta: { label: string; href: string };
  featured?: boolean;
  note?: string;
};

/**
 * Placeholder amounts. Change `price` here and the pricing section follows;
 * nothing else in the site hard-codes a number.
 */
export const PLANS: Plan[] = [
  {
    id: "trial",
    name: "Trial",
    price: "Free",
    cadence: "no card, no account",
    pitch:
      "The whole application, not a crippled preview. Every model, every export, every notes style.",
    features: [
      "One file at a time, up to ten minutes (or the first ten of longer recordings)",
      "Speaker diarization and word-level timestamps",
      "All six transcript formats plus PDF notes",
      "All twelve notes styles",
      "Runs offline once the models are downloaded",
    ],
    cta: { label: "Download the trial", href: "/download" },
    featured: true,
    note: "The only limits are one file and length. Nothing is watermarked or withheld.",
  },
  {
    id: "personal",
    name: "Personal",
    price: "$79",
    cadence: "one-time, one computer",
    pitch:
      "For the podcaster, researcher, student, or journalist who owns their tools instead of renting them.",
    features: [
      "Unlimited recording length",
      "Free updates within the major version",
      "Move your license between machines",
      "Email support",
    ],
    cta: { label: "Join the launch list", href: "/#waitlist" },
  },
  {
    id: "team",
    name: "Team",
    price: "$249",
    cadence: "one-time, five computers",
    pitch:
      "For the small team that records everything and wants none of it on someone else's servers.",
    features: [
      "Everything in Personal, on five machines",
      "Shared export presets and notes styles",
      "Priority support",
      "Invoice on request",
    ],
    cta: { label: "Join the launch list", href: "/#waitlist" },
    note: "Summit is desktop software. Each seat runs on its own hardware; there is no shared cloud workspace.",
  },
  {
    id: "business",
    name: "Business",
    price: "Talk to us",
    cadence: "volume and procurement",
    pitch:
      "For legal, healthcare, defence, and anyone whose compliance team asks where the audio goes.",
    features: [
      "Volume licensing and purchase orders",
      "Deployment notes for locked-down networks",
      "Security questionnaire support",
      "Named contact for onboarding",
    ],
    cta: { label: "Start a conversation", href: "/#waitlist" },
  },
];
