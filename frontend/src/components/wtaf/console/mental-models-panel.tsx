"use client";
/* ============ WTAF — console: the shared mental-model library, per agent ============ */
import { useState } from "react";
import type { AgentView } from "@/lib/api/wtaf";
import { LayerEditor, type LayerCtl } from "./layer-editor";

export function MentalModelsPanel({
  agent,
  ctl,
  onToggle,
  pending,
}: {
  agent: AgentView;
  ctl: LayerCtl;
  /** Enable/disable one framework for this agent (persists immediately). */
  onToggle: (key: string, enabled: boolean) => void;
  /** A toggle is in flight — disable the switches so clicks can't race. */
  pending: boolean;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const enabled = new Set(agent.mental_models);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div style={{ fontSize: 11.5, color: "var(--t-lo)", lineHeight: 1.5 }}>
        The reasoning frameworks {agent.name} applies before answering. The library is shared —
        editing the text of a framework changes it for every agent that runs it; the toggle only
        changes who runs it.
      </div>

      {ctl.prompts &&
        Object.values(ctl.prompts)
          .filter((p) => p.layer === "mental_model")
          .map((p) => {
            const on = enabled.has(p.key);
            const isOpen = open === p.key;
            return (
              <div
                key={p.key}
                style={{
                  borderRadius: 11,
                  border: "1px solid " + (on ? "var(--stroke-hi)" : "var(--stroke)"),
                  background: on ? "var(--panel-2)" : "transparent",
                  padding: "11px 13px",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
                  <button
                    type="button"
                    onClick={() => onToggle(p.key, !on)}
                    disabled={ctl.readOnly || pending}
                    aria-pressed={on}
                    title={on ? "Disable for this agent" : "Enable for this agent"}
                    style={{
                      width: 34,
                      height: 19,
                      borderRadius: 99,
                      flexShrink: 0,
                      position: "relative",
                      border: "1px solid " + (on ? "color-mix(in oklch, var(--orange-bright) 55%, transparent)" : "var(--stroke-hi)"),
                      background: on
                        ? "color-mix(in oklch, var(--orange-bright) 26%, transparent)"
                        : "var(--panel-2)",
                      cursor: ctl.readOnly || pending ? "default" : "pointer",
                      opacity: ctl.readOnly || pending ? 0.5 : 1,
                      transition: "background .15s",
                    }}
                  >
                    <span
                      style={{
                        position: "absolute",
                        top: 2,
                        left: on ? 16 : 2,
                        width: 13,
                        height: 13,
                        borderRadius: 99,
                        background: on ? "var(--orange-bright)" : "var(--t-faint)",
                        boxShadow: on ? "0 0 8px var(--orange-bright)" : "none",
                        transition: "left .15s",
                      }}
                    />
                  </button>

                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: 12.5,
                        fontWeight: 600,
                        color: on ? "var(--t-hi)" : "var(--t-mid)",
                      }}
                    >
                      {p.label}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--t-lo)", marginTop: 1 }}>
                      {p.description}
                    </div>
                  </div>

                  {p.is_overridden && (
                    <span
                      className="chip"
                      style={{
                        fontSize: 9,
                        color: "var(--amber)",
                        borderColor: "color-mix(in oklch, var(--amber) 40%, transparent)",
                      }}
                    >
                      edited
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => setOpen(isOpen ? null : p.key)}
                    className="mono"
                    style={{
                      fontSize: 10.5,
                      padding: "4px 9px",
                      borderRadius: 8,
                      background: "transparent",
                      border: "1px solid var(--stroke)",
                      color: "var(--t-mid)",
                      cursor: "pointer",
                    }}
                  >
                    {isOpen ? "close" : "edit text"}
                  </button>
                </div>

                {isOpen && (
                  <div style={{ marginTop: 12 }}>
                    <LayerEditor ctl={ctl} promptKey={p.key} rows={5} />
                  </div>
                )}
              </div>
            );
          })}
    </div>
  );
}
