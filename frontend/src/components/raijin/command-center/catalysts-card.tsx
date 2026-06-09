"use client";
import type { Catalyst } from "@/lib/types";
import { Card } from "../primitives";

export function CatalystsCard({ catalysts }: { catalysts: Catalyst[] }) {
  const toneC: Record<string, string> = { orange: "var(--orange)", blue: "var(--blue-bright)", green: "var(--up)", indigo: "var(--indigo)" };
  return (
    <Card title="Upcoming Catalysts" sub="key events" className="span5"
      action={<span className="label-xs" style={{ fontSize: 9 }}>next 7 days</span>}>
      <div style={{ display: "flex", flexDirection: "column" }}>
        {catalysts.map((c, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 13, padding: "9px 0", borderBottom: i < catalysts.length - 1 ? "1px solid var(--stroke)" : "none" }}>
            <div style={{ textAlign: "center", width: 34, flexShrink: 0 }}>
              <div className="mono display" style={{ fontSize: 18, fontWeight: 700, lineHeight: 1, color: "var(--t-hi)" }}>{c.d}</div>
              <div className="label-xs" style={{ fontSize: 8 }}>{c.m}</div>
            </div>
            <div style={{ width: 2, height: 26, borderRadius: 2, background: toneC[c.tone], boxShadow: `0 0 8px ${toneC[c.tone]}` }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12.5, fontWeight: 500 }}>{c.t}</div>
              <div className="mono" style={{ fontSize: 10.5, color: "var(--t-lo)", marginTop: 1 }}>{c.sub}</div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
