"use client";
import type { Agent, BriefingItem } from "@/lib/types";
import { Card } from "../primitives";
import { AgentAvatar } from "../agents";

export function BriefingCard({ briefing, freddy }: { briefing: BriefingItem[]; freddy: Agent }) {
  const toneColor: Record<string, string> = { up: "var(--up)", down: "var(--down)", neutral: "var(--amber)" };
  return (
    <Card title="Daily Briefing" sub="60-sec read" className="span3">
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 13 }}>
        <AgentAvatar a={freddy} size={28} />
        <div style={{ fontSize: 11.5, color: "var(--t-mid)" }}>Freddy · <span style={{ color: "var(--t-lo)" }}>allocator</span></div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {briefing.map((b, i) => (
          <div key={i} style={{ display: "flex", gap: 10 }}>
            <span style={{ width: 6, height: 6, borderRadius: 99, marginTop: 5, flexShrink: 0, background: toneColor[b.tone], boxShadow: `0 0 7px ${toneColor[b.tone]}` }} />
            <span style={{ fontSize: 12.5, lineHeight: 1.45, color: "var(--t-mid)", textWrap: "pretty" }}>{b.text}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
