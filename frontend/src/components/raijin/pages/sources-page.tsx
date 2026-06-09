"use client";
/* ============ RAIJIN — Sources & Prediction Ledger ============ */
import { useState } from "react";
import { useRaijinData } from "@/providers/raijin-provider";
import { setSourceLive } from "@/lib/api/raijin";
import { Card } from "../primitives";
import { PageHead } from "../shared";

export function SourcesPage() {
  const d = useRaijinData();
  const [sources, setSources] = useState(d.sources);

  const toggle = (name: string, next: boolean) => {
    // optimistic update, then persist via API
    setSources((s) => s.map((x) => (x.name === name ? { ...x, live: next } : x)));
    setSourceLive(name, next).catch(() => {
      // rollback on failure
      setSources((s) => s.map((x) => (x.name === name ? { ...x, live: !next } : x)));
    });
  };

  return (
    <div>
      <PageHead title="Sources & Agent Management" sub="data feeds · prediction accuracy ledger" />
      <div className="grid12">
        <Card title="Data Sources" sub={`${sources.filter((s) => s.live).length} live`} className="span6"
          action={<button className="primary-btn" style={{ padding: "6px 12px", fontSize: 11.5 }}>+ Add Source</button>}>
          <div style={{ display: "flex", flexDirection: "column" }}>
            {sources.map((s, i) => (
              <div key={s.name} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: i < sources.length - 1 ? "1px solid var(--stroke)" : "none" }}>
                <span className="chip" style={{ fontSize: 9, width: 58, justifyContent: "center" }}>{s.kind}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12.5, fontWeight: 500 }}>{s.name}</div>
                  <div className="mono" style={{ fontSize: 10, color: "var(--t-lo)" }}>{s.freq} · {s.items} items</div>
                </div>
                <button onClick={() => toggle(s.name, !s.live)} style={{ width: 38, height: 21, borderRadius: 99, padding: 2, background: s.live ? "color-mix(in oklch, var(--up) 55%, transparent)" : "rgba(255,255,255,0.1)", border: "none", display: "flex" }}>
                  <span style={{ width: 17, height: 17, borderRadius: 99, background: "#fff", transform: `translateX(${s.live ? 17 : 0}px)`, transition: "transform .18s", boxShadow: "0 1px 3px rgba(0,0,0,0.4)" }} />
                </button>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Prediction Ledger" sub="channel accuracy · Brier-scored" className="span6">
          <div style={{ display: "grid", gridTemplateColumns: "24px 1fr 56px 56px 50px", gap: 8, padding: "0 0 8px", borderBottom: "1px solid var(--stroke)" }}>
            {["#", "Channel", "Acc", "Pred", "Brier"].map((h, i) => (<span key={i} className="label-xs" style={{ fontSize: 8.5, textAlign: i > 1 ? "right" : "left" }}>{h}</span>))}
          </div>
          {d.ledger.map((l, i) => (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "24px 1fr 56px 56px 50px", gap: 8, alignItems: "center", padding: "9px 0", borderBottom: i < d.ledger.length - 1 ? "1px solid var(--stroke)" : "none" }}>
              <span className="mono display" style={{ fontSize: 13, fontWeight: 700, color: l.rank === 1 ? "var(--amber)" : "var(--t-lo)" }}>{l.rank}</span>
              <span style={{ fontSize: 12.5, display: "flex", alignItems: "center", gap: 6 }}>{l.name}
                <span style={{ fontSize: 9, color: l.trend === "up" ? "var(--up)" : l.trend === "down" ? "var(--down)" : "var(--t-faint)" }}>{l.trend === "up" ? "▲" : l.trend === "down" ? "▼" : "—"}</span></span>
              <span className="mono" style={{ fontSize: 12, textAlign: "right", color: "var(--up)" }}>{(l.acc * 100) | 0}%</span>
              <span className="mono" style={{ fontSize: 12, textAlign: "right", color: "var(--t-mid)" }}>{l.n}</span>
              <span className="mono" style={{ fontSize: 11.5, textAlign: "right", color: "var(--t-lo)" }}>{l.brier}</span>
            </div>
          ))}
        </Card>

        <Card title="Pending Predictions" sub="awaiting resolution" className="span12">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 9 }}>
            {d.predictions.map((p, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 13px", borderRadius: 10, background: "var(--inset)", border: "1px solid var(--stroke)" }}>
                <span style={{ width: 7, height: 7, borderRadius: 99, background: "var(--amber)", boxShadow: "0 0 7px var(--amber)", flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12.5 }}>{p.claim}</div>
                  <div className="mono" style={{ fontSize: 10, color: "var(--t-lo)", marginTop: 2 }}>{p.by}</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className="mono" style={{ fontSize: 11.5, color: "var(--amber)" }}>{p.resolve}</div>
                  <div className="label-xs" style={{ fontSize: 8 }}>resolve by</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
