"use client";
/* ============ WTAF — Macro Indicators ============ */
import { useState } from "react";
import { useWtaf, useWtafData } from "@/providers/wtaf-provider";
import { Card, EmptyState } from "../primitives";
import { IndicatorCards } from "../indicator-cards";
import { SignpostsCard } from "../signposts-card";
import { PageHead, PageButton } from "../shared";
import { deskTakesFor, stanceFor, STANCE_COLOR } from "@/lib/stance";

const PAGE_SIZE = 8;

export function IndicatorsPage() {
  const d = useWtafData();
  const { discovering } = useWtaf();

  const [page, setPage] = useState(0);
  // The stance is the point of this card, so called names lead — otherwise, with only a
  // desk or two reporting, page 1 can be entirely UNRATED and say nothing. Sorting is
  // stable, so mention-count order survives inside each group.
  const stances = d.watchlist.map((w) => ({ w, ...stanceFor(deskTakesFor(d.deskNotes, w.t)) }));
  const ranked = [
    ...stances.filter((s) => s.stance !== "UNRATED"),
    ...stances.filter((s) => s.stance === "UNRATED"),
  ];
  const pageCount = Math.max(1, Math.ceil(ranked.length / PAGE_SIZE));
  // Clamp during render so a shrinking list (e.g. after re-discovery) never lands on an empty page.
  const safePage = Math.min(page, pageCount - 1);
  const watchPage = ranked.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);
  return (
    <div>
      <PageHead title="Macro Indicators" sub="macro regime · cycle signposts · evidence-backed" />
      <div className="grid12">
        <SignpostsCard />
        <IndicatorCards />
        {/* Stance and its one-liner both come from the Andie desks' StockTake (conviction
            -1..+1 + rationale), not from `sig` — which the live adapter fills with a
            normalised mention count, so it says how loud a ticker is, never which way. */}
        <Card title="Watchlist Snapshot" sub="US equities · desk conviction" className="span6"
          loading={discovering && d.watchlist.length === 0} updating={discovering && d.watchlist.length > 0}>
          {d.watchlist.length === 0 ? (
            <EmptyState label="No tickers yet" sub="run a discovery" />
          ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {watchPage.map(({ w, stance, rationale }, i) => (
              <div key={w.t} style={{ display: "flex", alignItems: "center", gap: 12, padding: "9px 0", borderBottom: i < watchPage.length - 1 ? "1px solid var(--stroke)" : "none" }}>
                <span className="mono" style={{ fontSize: 12.5, fontWeight: 600, width: 54, flexShrink: 0 }}>{w.t}</span>
                <div style={{ flex: 1, minWidth: 0, fontSize: 11.5, lineHeight: 1.4, textWrap: "pretty", color: rationale ? "var(--t-lo)" : "var(--t-faint)" }}>
                  {rationale || "No desk call yet."}
                </div>
                <span className="chip" style={{ flexShrink: 0, color: STANCE_COLOR[stance], borderColor: `color-mix(in oklch, ${STANCE_COLOR[stance]} 40%, transparent)` }}>{stance}</span>
              </div>
            ))}
            {pageCount > 1 && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--stroke)" }}>
                <PageButton label="‹ Prev" disabled={safePage === 0} onClick={() => setPage(safePage - 1)} />
                <span className="mono" style={{ fontSize: 11.5, color: "var(--t-mid)" }}>Page {safePage + 1} of {pageCount}</span>
                <PageButton label="Next ›" disabled={safePage >= pageCount - 1} onClick={() => setPage(safePage + 1)} />
              </div>
            )}
          </div>
          )}
        </Card>
        <Card title="Key Events" sub="past & upcoming" className="span6">
          {d.catalysts.length === 0 ? (
            <EmptyState label="No events yet" sub="Awaiting Tier 3–5" />
          ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {d.catalysts.map((c, i) => (
              <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "8px 0", borderBottom: i < d.catalysts.length - 1 ? "1px solid var(--stroke)" : "none" }}>
                <span className="mono" style={{ fontSize: 11, color: "var(--t-lo)", width: 46, flexShrink: 0, lineHeight: 1.5 }}>{c.d} {c.m}</span>
                <span style={{ fontSize: 12.5, flex: 1, minWidth: 0, lineHeight: 1.35, overflowWrap: "anywhere" }}>{c.t}</span>
                <span className="mono" style={{ fontSize: 10.5, color: "var(--t-faint)", flexShrink: 0, whiteSpace: "nowrap", lineHeight: 1.6 }}>{c.sub.split(" · ")[0]}</span>
              </div>
            ))}
          </div>
          )}
        </Card>
      </div>
    </div>
  );
}
