"use client";
/* ============ WTAF — Signal & Tracker Terminal ============ */
import { useState } from "react";
import type { WtafData } from "@/lib/types";
import { useWtafData } from "@/providers/wtaf-provider";
import { Card, Spark } from "../primitives";
import { PageHead, Stat } from "../shared";

function Heatmap({ d }: { d: WtafData }) {
  const weeks = 8;
  const cellColor = (s: number) => {
    if (s > 0.05) return `color-mix(in oklch, var(--up) ${Math.min(85, 30 + s * 70)}%, transparent)`;
    if (s < -0.05) return `color-mix(in oklch, var(--down) ${Math.min(85, 30 + -s * 70)}%, transparent)`;
    return "rgba(255,255,255,0.05)";
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <div style={{ display: "grid", gridTemplateColumns: "150px repeat(8, 1fr) 56px", gap: 5, alignItems: "center" }}>
        <span />
        {Array.from({ length: weeks }).map((_, i) => (<span key={i} className="label-xs" style={{ fontSize: 8, textAlign: "center" }}>W{i + 1}</span>))}
        <span className="label-xs" style={{ fontSize: 8, textAlign: "right" }}>now</span>
      </div>
      {d.indicators.map((ind, r) => {
        const series = Array.from({ length: weeks }).map((_, i) => ind.score * (0.4 + 0.6 * (i / (weeks - 1))) + Math.sin(r + i) * 0.12);
        return (
          <div key={r} style={{ display: "grid", gridTemplateColumns: "150px repeat(8, 1fr) 56px", gap: 5, alignItems: "center" }}>
            <span style={{ fontSize: 11.5, color: "var(--t-mid)" }}>{ind.name}</span>
            {series.map((s, i) => (
              <div key={i} title={s.toFixed(2)} style={{ height: 24, borderRadius: 5, background: cellColor(s), border: "1px solid rgba(255,255,255,0.04)" }} />
            ))}
            <span className="mono" style={{ fontSize: 11, textAlign: "right", color: ind.score >= 0 ? "var(--up)" : "var(--down)" }}>{ind.score >= 0 ? "+" : ""}{ind.score.toFixed(2)}</span>
          </div>
        );
      })}
    </div>
  );
}

export function SignalTerminal({
  onOpenContext,
  onNewTracker,
}: {
  onOpenContext: (trackerName: string) => void;
  onNewTracker: () => void;
}) {
  const d = useWtafData();
  const [sel, setSel] = useState(0);
  const t = d.trackers[sel];
  const toneC: Record<string, string> = { up: "var(--up)", down: "var(--down)", flat: "var(--blue)" };
  const big = t.spark.flatMap((v, i) => (i ? [(t.spark[i - 1] + v) / 2, v] : [v]));
  return (
    <div>
      <PageHead title="Signal & Tracker Terminal" sub="semantic concept tracking · channel-level"
        right={<button onClick={onNewTracker} className="primary-btn">+ New Tracker</button>} />
      <div className="grid12">
        <Card title="Trackers" sub={`${d.trackers.length}/15`} className="span3" pad={false}>
          <div style={{ padding: "4px 8px 10px" }}>
            {d.trackers.map((tr, i) => (
              <button key={i} onClick={() => setSel(i)} style={{ display: "flex", alignItems: "center", gap: 9, width: "100%", textAlign: "left", padding: "9px 10px", borderRadius: 9, marginTop: 4, border: "1px solid " + (i === sel ? "var(--stroke-hi)" : "transparent"), background: i === sel ? "var(--panel-2)" : "transparent" }}>
                <span style={{ width: 5, height: 5, borderRadius: 99, background: toneC[tr.tone], boxShadow: `0 0 6px ${toneC[tr.tone]}`, flexShrink: 0 }} />
                <span style={{ flex: 1, fontSize: 12, color: i === sel ? "var(--t-hi)" : "var(--t-mid)" }}>{tr.name}</span>
                <span className="mono" style={{ fontSize: 11, color: "var(--t-lo)" }}>{tr.mentions}</span>
              </button>
            ))}
          </div>
        </Card>

        <Card title={t.name} sub={`${t.channels} channels · mentions over time`} className="span9"
          action={<button onClick={() => onOpenContext(t.name)} style={{ fontSize: 11, color: "var(--blue-bright)", background: "none", border: "none" }}>Context preview →</button>}>
          <div style={{ display: "flex", gap: 20, marginBottom: 8 }}>
            <Stat label="Mentions" value={t.mentions} />
            <Stat label="WoW" value={`${t.chg >= 0 ? "+" : ""}${t.chg}`} color={toneC[t.tone]} />
            <Stat label="Channels" value={t.channels} />
            <Stat label="Peak" value={t.tone === "up" ? "rising" : t.tone === "down" ? "fading" : "flat"} color={toneC[t.tone]} />
          </div>
          <div style={{ height: 170, position: "relative", marginTop: 4 }}>
            <Spark data={big} h={170} fill strokeW={2.6} color={toneC[t.tone]} />
            <div style={{ position: "absolute", inset: 0, display: "flex", justifyContent: "space-between", pointerEvents: "none" }}>
              {["9wk", "7wk", "5wk", "3wk", "now"].map((l, i) => (<span key={i} className="mono" style={{ fontSize: 9.5, color: "var(--t-faint)", alignSelf: "flex-end" }}>{l}</span>))}
            </div>
          </div>
          <div style={{ marginTop: 8, fontSize: 11, color: "var(--t-lo)" }}>Click any spike to open the exact transcript moment · jump-to-timestamp source link.</div>
        </Card>

        <Card title="Indicator Heatmap" sub="rubric scores · last 8 weeks" className="span12">
          <Heatmap d={d} />
        </Card>
      </div>
    </div>
  );
}
