/* ============ WTAF — display formatters ============ */
import type { WatchItem } from "./types";

/** Shown for price/change when there's no real market quote yet. */
export const NO_QUOTE = "—";

/**
 * A watchlist row carries a real market quote only when a price feed populated it.
 * There's no market-data tier yet, so the live adapter sets `px: 0` (and `chg: 0`) —
 * we treat `px === 0` as "no quote" so we don't render a misleading `+0.00%`. Mock
 * data uses non-zero prices, so this stays false there.
 */
export function hasQuote(w: Pick<WatchItem, "px">): boolean {
  return w.px !== 0;
}

export function fmtPrice(w: Pick<WatchItem, "px">): string {
  return hasQuote(w) ? w.px.toFixed(2) : NO_QUOTE;
}

export function fmtChange(w: Pick<WatchItem, "px" | "chg">): string {
  return hasQuote(w) ? `${w.chg >= 0 ? "+" : ""}${w.chg.toFixed(2)}%` : NO_QUOTE;
}
