"use client";
import type { Ace } from "@/lib/types";
import { Card, Delta, Ring, MiniBar } from "../primitives";

export function AceCard({ ace }: { ace: Ace }) {
  const fill = (ace.value + 1) / 2;
  return (
    <Card title="ACE Index" sub="AI Capital Environment" className="span3"
      action={<span className="chip" style={{ borderColor: "var(--stroke-hi)" }}>composite</span>}>
      <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
        <Ring value={fill} size={128} stroke={10} from="blue" to="indigo">
          <div>
            <div className="mono display" style={{ fontSize: 30, fontWeight: 700, color: "var(--t-hi)", lineHeight: 1 }}>
              {ace.value > 0 ? "+" : ""}{ace.value.toFixed(2)}</div>
            <div className="label-xs" style={{ fontSize: 8, marginTop: 4, color: "var(--blue-bright)" }}>{ace.label}</div>
          </div>
        </Ring>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 13 }}>
          {ace.components.map((c, i) => (
            <div key={i}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 5 }}>
                <span style={{ fontSize: 11, color: "var(--t-mid)" }}>{c.key} <span className="mono" style={{ fontSize: 9, color: "var(--t-faint)" }}>· {(c.weight * 100) | 0}%</span></span>
                <span className="mono" style={{ fontSize: 11, color: c.score >= 0 ? "var(--up)" : "var(--down)" }}>{c.score >= 0 ? "+" : ""}{c.score.toFixed(2)}</span>
              </div>
              <MiniBar v={(c.score + 1) / 2} color="var(--blue-bright)" />
            </div>
          ))}
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 13, paddingTop: 12, borderTop: "1px solid var(--stroke)" }}>
        <Delta v={ace.delta} suffix="" size={11} />
        <span style={{ fontSize: 11, color: "var(--t-lo)" }}>vs last week · tracks $SMH / $QQQ</span>
      </div>
    </Card>
  );
}
