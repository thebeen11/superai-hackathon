"use client";
import type { WatchItem } from "@/lib/types";
import { Card } from "../primitives";

export function WatchlistCard({ watchlist }: { watchlist: WatchItem[] }) {
  return (
    <Card title="Watchlist" sub="bottom-up" className="span4"
      action={<span className="mono" style={{ fontSize: 11, color: "var(--orange-bright)" }}>3 alerts</span>}>
      <div style={{ display: "flex", flexDirection: "column" }}>
        {watchlist.map((w, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 0", borderBottom: i < watchlist.length - 1 ? "1px solid var(--stroke)" : "none" }}>
            <span className="mono" style={{ fontSize: 12.5, fontWeight: 600, width: 52 }}>{w.t}</span>
            <span style={{ fontSize: 11, color: "var(--t-lo)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{w.n}</span>
            {w.alert && <span className="chip" style={{ fontSize: 9.5, padding: "2px 6px", borderColor: "color-mix(in oklch, var(--orange) 40%, transparent)", color: "var(--orange-bright)" }}>{w.alert}</span>}
            <span className="mono" style={{ fontSize: 12, width: 62, textAlign: "right" }}>{w.px.toFixed(2)}</span>
            <span className="mono" style={{ fontSize: 11.5, width: 54, textAlign: "right", color: w.chg >= 0 ? "var(--up)" : "var(--down)" }}>{w.chg >= 0 ? "+" : ""}{w.chg.toFixed(2)}%</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
