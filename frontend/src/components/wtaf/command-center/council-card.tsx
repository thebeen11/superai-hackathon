"use client";
import type { Agent, Tier } from "@/lib/types";
import { Card, Dot } from "../primitives";
import { TierFlow } from "../agents";

export function CouncilCard({
  tiers,
  onOpenAgent,
}: {
  tiers: Tier[];
  onOpenAgent: (agentId: string) => void;
}) {
  const agentCount = tiers.reduce((n, t) => n + t.squad.length, 0);
  return (
    <Card title="Agent Council" sub={`${tiers.length} tiers · ${agentCount} agents`} className="span9"
      action={<div style={{ display: "flex", alignItems: "center", gap: 6 }}><Dot tone="blue" /><span className="mono" style={{ fontSize: 11, color: "var(--t-mid)" }}>DAG active</span></div>}>
      <TierFlow tiers={tiers} onOpenAgent={(a: Agent) => onOpenAgent(a.id)} />
    </Card>
  );
}
