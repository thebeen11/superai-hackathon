"use client";
import type { Agent, BriefingItem } from "@/lib/types";
import { Card, EmptyState } from "../primitives";
import { AgentAvatar } from "../agents";

export function BriefingCard({
  briefing,
  chairman,
}: {
  briefing: BriefingItem[];
  chairman: Agent;
}) {
  const toneColor: Record<string, string> = {
    up: "var(--up)",
    down: "var(--down)",
    neutral: "var(--amber)",
  };
  return (
    <Card title="Chairman’s Briefing" sub="60-sec read" className="span3">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 9,
          marginBottom: 13,
        }}
      >
        <AgentAvatar a={chairman} size={28} />
        <div style={{ fontSize: 11.5, color: "var(--t-mid)" }}>
          Winston · <span style={{ color: "var(--t-lo)" }}>chairman</span>
        </div>
      </div>
      {briefing.length === 0 && (
        <EmptyState
          label="No briefing yet"
          sub="Awaiting Winston (Tier 5)"
          minHeight={120}
        />
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {briefing.map((b, i) => (
          <div key={i} style={{ display: "flex", gap: 10 }}>
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: 99,
                marginTop: 5,
                flexShrink: 0,
                background: toneColor[b.tone],
                boxShadow: `0 0 7px ${toneColor[b.tone]}`,
              }}
            />
            <span
              style={{
                fontSize: 12.5,
                lineHeight: 1.45,
                color: "var(--t-mid)",
                textWrap: "pretty",
              }}
            >
              {b.text}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}
