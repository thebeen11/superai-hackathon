"use client";
import type { Agent, PipelineStage } from "@/lib/types";
import { Card, Dot } from "../primitives";
import { AgentRow, PipelineFlow } from "../agents";

export function CouncilCard({
  agents,
  pipeline,
  onOpenAgent,
}: {
  agents: Agent[];
  pipeline: PipelineStage[];
  onOpenAgent: (agentId: string) => void;
}) {
  return (
    <Card
      title="Agent Council"
      sub="4 agents · live"
      className="span9"
      action={
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Dot tone="blue" />
          <span
            className="mono"
            style={{ fontSize: 11, color: "var(--t-mid)" }}
          >
            pipeline active
          </span>
        </div>
      }
    >
      <div style={{ display: "flex", gap: 16 }}>
        <div style={{ flex: 1.3, display: "flex", flexDirection: "column" }}>
          {agents.map((a) => (
            <AgentRow key={a.id} a={a} onClick={() => onOpenAgent(a.id)} />
          ))}
        </div>
        <div style={{ width: 1, background: "var(--stroke)" }} />
        <div style={{ flex: 1, paddingTop: 4 }}>
          <div className="label-xs" style={{ marginBottom: 11 }}>
            Pipeline status
          </div>
          <PipelineFlow pipeline={pipeline} />
          <div
            style={{
              marginTop: 13,
              padding: "10px 12px",
              borderRadius: 10,
              background: "var(--inset)",
              border: "1px solid var(--stroke)",
            }}
          >
            <div
              className="mono"
              style={{
                fontSize: 11,
                color: "var(--orange-bright)",
                display: "flex",
                alignItems: "center",
                gap: 7,
                whiteSpace: "nowrap",
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: 99,
                  flexShrink: 0,
                  background: "var(--orange)",
                  boxShadow: "0 0 7px var(--orange)",
                  animation: "pulse-dot 1.6s infinite",
                }}
              />
              Andie · scoring 2 transcripts
            </div>
            <div
              className="mono"
              style={{
                fontSize: 10.5,
                color: "var(--t-lo)",
                marginTop: 5,
                whiteSpace: "nowrap",
              }}
            >
              Wilfred · 3 sources · ~4 min ETA
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}
