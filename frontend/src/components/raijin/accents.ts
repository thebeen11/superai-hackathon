import type { AccentKey } from "@/lib/types";

export const ACCENTS: Record<AccentKey, { c: string; g: string }> = {
  blue: { c: "var(--blue)", g: "var(--blue-bright)" },
  indigo: { c: "var(--indigo)", g: "var(--blue-bright)" },
  orange: { c: "var(--orange)", g: "var(--orange-bright)" },
  green: { c: "var(--up)", g: "var(--up)" },
  red: { c: "var(--down)", g: "var(--down)" },
  amber: { c: "var(--amber)", g: "var(--amber)" },
  chair: { c: "oklch(0.88 0.05 250)", g: "oklch(0.97 0.02 250)" },
};

/** Maps an agent/pipeline status string to an accent key. */
export const STATE_TONE: Record<string, AccentKey> = {
  active: "blue",
  thinking: "orange",
  idle: "green",
  done: "green",
  progress: "orange",
  pending: "red",
};
