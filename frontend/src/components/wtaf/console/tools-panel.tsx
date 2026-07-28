"use client";
/* ============ WTAF — console: an agent's tools (read-only, declared in code) ============ */
import type { AgentView } from "@/lib/api/wtaf";
import { EmptyState } from "../primitives";

export function ToolsPanel({ agent }: { agent: AgentView }) {
  if (agent.tools.length === 0) {
    return <EmptyState label="No tools" sub="This agent reasons only over what it is handed." />;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
      <div style={{ fontSize: 11.5, color: "var(--t-lo)", lineHeight: 1.5 }}>
        The executable functions {agent.name} may call. Tools are defined in the backend, not the
        console — this list is what the code actually wires up.
      </div>
      {agent.tools.map((t) => (
        <div
          key={t.name}
          style={{
            padding: "11px 13px",
            borderRadius: 11,
            background: "var(--inset)",
            border: "1px solid var(--stroke)",
          }}
        >
          <div style={{ display: "flex", alignItems: "baseline", gap: 9, flexWrap: "wrap" }}>
            <span className="mono" style={{ fontSize: 12.5, fontWeight: 600, color: "var(--blue-bright)" }}>
              {t.name}
            </span>
            <span className="chip mono" style={{ fontSize: 9.5, color: "var(--t-faint)" }}>
              {t.module}
            </span>
          </div>
          <div style={{ fontSize: 11.5, color: "var(--t-mid)", marginTop: 4, lineHeight: 1.45 }}>
            {t.description}
          </div>
          <div className="mono" style={{ fontSize: 10.5, color: "var(--t-lo)", marginTop: 5 }}>
            {t.io}
          </div>
        </div>
      ))}
    </div>
  );
}
