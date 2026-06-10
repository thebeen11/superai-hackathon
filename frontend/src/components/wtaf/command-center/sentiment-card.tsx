"use client";
import type { Sentiment } from "@/lib/types";
import { Card, Spark } from "../primitives";

export function SentimentCard({ sentiment, discovering = false }: { sentiment: Sentiment; discovering?: boolean }) {
  const s = sentiment;
  const isEmpty = s.wave.length === 0;
  const moodColor = s.moodTone === "up" ? "var(--up)" : s.moodTone === "down" ? "var(--down)" : "var(--amber)";
  // High volatility = caution (red), low = calm (green).
  const volColor = s.vol === "HIGH" ? "var(--down)" : s.vol === "LOW" ? "var(--up)" : "var(--t-mid)";
  return (
    <Card title="Market Sentiment" sub="aggregate · 14 sources" className="span5"
      loading={discovering && isEmpty} updating={discovering && !isEmpty}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 6, gap: 8 }}>
        <div style={{ flexShrink: 0 }}>
          <div className="display" style={{ fontSize: 23, fontWeight: 600, color: moodColor, whiteSpace: "nowrap" }}>{s.mood}</div>
          <div className="label-xs" style={{ fontSize: 9, marginTop: 2 }}>mood signal</div>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <div className="mono" style={{ fontSize: 13, color: "var(--t-mid)" }}>vol <span style={{ color: volColor }}>{s.vol}</span></div>
          <div className="label-xs" style={{ fontSize: 9, marginTop: 2 }}>volatility</div>
        </div>
      </div>
      <div style={{ height: 64, marginTop: 4 }}><Spark data={s.wave} h={64} fill color="var(--blue-bright)" /></div>
    </Card>
  );
}
