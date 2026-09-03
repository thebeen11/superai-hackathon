/* ============ WTAF — per-ticker stance (Andie desk conviction → band) ============ */
import type { DeskNote, Stance, StockTake } from "./types";

export type { Stance };

export interface DeskTake {
  desk: string;
  take: StockTake;
}

export interface StanceRead {
  stance: Stance;
  /** Mean desk conviction (-1..+1), or null when nothing was called. */
  conviction: number | null;
  /** The strongest desk's one-line rationale; empty when unrated. */
  rationale: string;
}

/**
 * ±0.2, the same cut the backend uses to band its own -1..+1 scores
 * (`_band` in backend/app/council/chairman.py). Keeping the two in step means an
 * indicator and a ticker scored alike read alike.
 */
const BAND_EDGE = 0.2;

export const STANCE_COLOR: Record<Stance, string> = {
  BULLISH: "var(--up)",
  NEUTRAL: "var(--amber)",
  BEARISH: "var(--down)",
  UNRATED: "var(--t-faint)",
};

/**
 * The desk calls on one ticker.
 *
 * Watchlist rows carry the bare symbol ("NVDA") while the desks key on the "$NVDA"
 * canonical the backend resolves entities to, so the join normalises both sides.
 */
export function deskTakesFor(deskNotes: DeskNote[], ticker: string): DeskTake[] {
  const sym = `$${ticker.replace(/^\$/, "").toUpperCase()}`;
  return deskNotes.flatMap((n) =>
    n.stocks
      .filter((s) => s.ticker.toUpperCase() === sym)
      .map((take) => ({ desk: n.desk, take })),
  );
}

/**
 * Fold desk calls into one stance.
 *
 * The desks hold disjoint sectors, so a ticker normally has exactly one take. When two
 * desks do land on the same name we average their conviction rather than picking one,
 * and show the rationale of whichever argued hardest — so a second view moves the band
 * instead of disappearing.
 */
export function stanceFor(takes: DeskTake[]): StanceRead {
  if (takes.length === 0) return { stance: "UNRATED", conviction: null, rationale: "" };

  const conviction =
    takes.reduce((sum, { take }) => sum + take.conviction, 0) / takes.length;
  const loudest = takes.reduce((a, b) =>
    Math.abs(b.take.conviction) > Math.abs(a.take.conviction) ? b : a,
  );

  return {
    stance: conviction > BAND_EDGE ? "BULLISH" : conviction < -BAND_EDGE ? "BEARISH" : "NEUTRAL",
    conviction,
    rationale: loudest.take.rationale,
  };
}

/**
 * A theme's stance, from Winston's read on the fixed theme taxonomy
 * (`backend/app/council/theme_reads.py`).
 *
 * `evidenced=false` is the backend saying nothing in the corpus spoke to the theme, so it
 * reads UNRATED rather than as a Neutral *call* — the two look alike in the payload and
 * mean very different things. A directional stance is already guaranteed grounded there:
 * an ungrounded Bullish/Bearish is downgraded before it is ever persisted.
 */
export function themeStance(read: { stance?: string; evidenced?: boolean } | undefined): Stance {
  if (!read || read.evidenced === false) return "UNRATED";
  switch ((read.stance ?? "").trim().toUpperCase()) {
    case "BULLISH": return "BULLISH";
    case "BEARISH": return "BEARISH";
    case "NEUTRAL": return "NEUTRAL";
    default: return "UNRATED";
  }
}
