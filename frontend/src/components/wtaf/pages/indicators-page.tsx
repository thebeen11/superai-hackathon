"use client";
/* ============ WTAF — Financial Indicator Dashboard ============ */
import { useWtaf, useWtafData } from "@/providers/wtaf-provider";
import { Card, Ring, MiniBar, EmptyState } from "../primitives";
import { PageHead } from "../shared";
import { fmtChange, hasQuote } from "@/lib/format";

export function IndicatorsPage() {
  const d = useWtafData();
  const { discovering } = useWtaf();
  const bandC: Record<string, string> = { Positive: "var(--up)", Neutral: "var(--amber)", Negative: "var(--down)" };
  return (
    <div>
      <PageHead title="Financial Indicator Dashboard" sub="industry signal coverage · evidence-backed" />
      <div className="grid12">
        {d.indicators.length === 0 && (
          <Card className="span12" loading={discovering}>
            <EmptyState label="No indicators yet" sub="Run a discovery to derive industry signals · rubric scores await Tier 3 (Andie)" />
          </Card>
        )}
        {d.indicators.map((ind, i) => (
          <Card key={i} className="span4" title={ind.name} sub={ind.band}>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <Ring value={(ind.score + 1) / 2} size={78} stroke={7} from={ind.score >= 0 ? "green" : "red"} to={ind.score >= 0 ? "blue" : "orange"}>
                <div className="mono display" style={{ fontSize: 15, fontWeight: 700, color: ind.score >= 0 ? "var(--up)" : "var(--down)" }}>{ind.score >= 0 ? "+" : ""}{ind.score.toFixed(1)}</div>
              </Ring>
              <div style={{ flex: 1 }}>
                <span className="chip" style={{ color: bandC[ind.band], borderColor: `color-mix(in oklch, ${bandC[ind.band]} 40%, transparent)` }}>{ind.band}</span>
                <div style={{ fontSize: 11.5, color: "var(--t-lo)", marginTop: 8, lineHeight: 1.4, textWrap: "pretty" }}>{ind.evid}</div>
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
            {d.watchlist.map((w, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 0", borderBottom: i < d.watchlist.length - 1 ? "1px solid var(--stroke)" : "none" }}>
                <span className="mono" style={{ fontSize: 12.5, fontWeight: 600, width: 54 }}>{w.t}</span>
                <div style={{ flex: 1 }}><MiniBar v={(w.sig + 1) / 2} color={w.sig >= 0 ? "var(--up)" : "var(--down)"} h={4} /></div>
                <span className="mono" style={{ fontSize: 11.5, width: 54, textAlign: "right", color: !hasQuote(w) ? "var(--t-faint)" : w.chg >= 0 ? "var(--up)" : "var(--down)" }}>{fmtChange(w)}</span>
              </div>
            ))}
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
