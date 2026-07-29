"use client";
/* ============ WTAF — Macro Indicators ============ */
import { useState } from "react";
import { useWtaf, useWtafData } from "@/providers/wtaf-provider";
import { Card, Ring, MiniBar, EmptyState } from "../primitives";
import { SignpostsCard } from "../signposts-card";
import { PageHead, PageButton } from "../shared";
import { EvidenceList } from "../source-link";
import { fmtChange, hasQuote } from "@/lib/format";

const PAGE_SIZE = 8;

export function IndicatorsPage() {
  const d = useWtafData();
  const { discovering } = useWtaf();
  const bandC: Record<string, string> = { Positive: "var(--up)", Neutral: "var(--amber)", Negative: "var(--down)" };

  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(d.watchlist.length / PAGE_SIZE));
  // Clamp during render so a shrinking list (e.g. after re-discovery) never lands on an empty page.
  const safePage = Math.min(page, pageCount - 1);
  const watchPage = d.watchlist.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);
  return (
    <div>
      <PageHead title="Macro Indicators" sub="macro regime · cycle signposts · evidence-backed" />
      <div className="grid12">
        <SignpostsCard />
        {d.indicators.length === 0 && (
          <Card className="span12" loading={discovering}>
            <EmptyState label="No indicators yet" sub="Run a discovery to derive industry signals · rubric scores await Tier 3 (Andie)" />
          </Card>
        )}
        {d.indicators.map((ind, i) => (
          <Card key={i} className="span4" title={ind.name}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <Ring value={(ind.score + 1) / 2} size={78} stroke={7} from={ind.score >= 0 ? "green" : "red"} to={ind.score >= 0 ? "blue" : "orange"}>
                <div className="mono display" style={{ fontSize: 15, fontWeight: 700, color: ind.score >= 0 ? "var(--up)" : "var(--down)" }}>{ind.score >= 0 ? "+" : ""}{ind.score.toFixed(1)}</div>
              </Ring>
              <div style={{ flex: 1 }}>
                <span className="chip" style={{ color: bandC[ind.band], borderColor: `color-mix(in oklch, ${bandC[ind.band]} 40%, transparent)` }}>{ind.band}</span>
                <div style={{ fontSize: 11.5, color: "var(--t-lo)", marginTop: 8, lineHeight: 1.4, textWrap: "pretty" }}>{ind.rationale}</div>
                <EvidenceList items={ind.evidence} sources={d.sourceDocs} emptyLabel="not source-anchored" />
              </div>
            </div>
          </Card>
        ))}
        <Card title="Watchlist Snapshot" sub="US equities" className="span6"
          loading={discovering && d.watchlist.length === 0} updating={discovering && d.watchlist.length > 0}>
          {d.watchlist.length === 0 ? (
            <EmptyState label="No tickers yet" sub="run a discovery" />
          ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {watchPage.map((w, i) => (
              <div key={w.t} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 0", borderBottom: i < watchPage.length - 1 ? "1px solid var(--stroke)" : "none" }}>
                <span className="mono" style={{ fontSize: 12.5, fontWeight: 600, width: 54 }}>{w.t}</span>
                <div style={{ flex: 1 }}><MiniBar v={(w.sig + 1) / 2} color={w.sig >= 0 ? "var(--up)" : "var(--down)"} h={4} /></div>
                <span className="mono" style={{ fontSize: 11.5, width: 54, textAlign: "right", color: !hasQuote(w) ? "var(--t-faint)" : w.chg >= 0 ? "var(--up)" : "var(--down)" }}>{fmtChange(w)}</span>
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
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 0", borderBottom: i < d.catalysts.length - 1 ? "1px solid var(--stroke)" : "none" }}>
                <span className="mono" style={{ fontSize: 11, color: "var(--t-lo)", width: 46 }}>{c.d} {c.m}</span>
                <span style={{ fontSize: 12.5, flex: 1 }}>{c.t}</span>
                <span className="mono" style={{ fontSize: 10.5, color: "var(--t-faint)" }}>{c.sub.split(" · ")[0]}</span>
              </div>
            ))}
          </div>
          )}
        </Card>
      </div>
    </div>
  );
}
