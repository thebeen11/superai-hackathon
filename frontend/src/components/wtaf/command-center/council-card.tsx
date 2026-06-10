"use client";
import type { Agent, Tier } from "@/lib/types";
import { useWtaf } from "@/providers/wtaf-provider";
import { Card, Dot } from "../primitives";
import { TierFlow } from "../agents";

export function CouncilCard({
  tiers,
  onOpenAgent,
}: {
  tiers: Tier[];
  onOpenAgent: (agentId: string) => void;
}) {
  const { liveStatus, discovering } = useWtaf();
  const agentCount = tiers.reduce((n, t) => n + t.squad.length, 0);
  return (
    <Card title="Agent Council" sub={`${tiers.length} tiers · ${agentCount} agents`} className="span8"
      action={<div style={{ display: "flex", alignItems: "center", gap: 6 }}><Dot tone={discovering ? "orange" : "blue"} pulse={discovering} /><span className="mono" style={{ fontSize: 11, color: "var(--t-mid)" }}>{discovering ? "running" : "DAG active"}</span></div>}>
      <TierFlow tiers={tiers} liveStatus={liveStatus} onOpenAgent={(a: Agent) => onOpenAgent(a.id)} />
    </Card>
  );
}
