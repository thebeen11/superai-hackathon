"use client";
/* ============ RAIJIN — small shared building blocks ============ */
import type { ReactNode } from "react";

export function PageHead({ title, sub, right }: { title: string; sub: string; right?: ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 16 }}>
      <div>
        <h2 className="display" style={{ fontSize: 20, fontWeight: 600 }}>{title}</h2>
        <div className="mono" style={{ fontSize: 11.5, color: "var(--t-lo)", marginTop: 2 }}>{sub}</div>
      </div>
      {right}
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="label-xs" style={{ marginBottom: 8 }}>{label}</div>
      {children}
    </div>
  );
}

export function Stat({ label, value, color }: { label: string; value: ReactNode; color?: string }) {
  return (
    <div>
      <div className="mono display" style={{ fontSize: 22, fontWeight: 700, color: color || "var(--t-hi)" }}>{value}</div>
      <div className="label-xs" style={{ fontSize: 8.5, marginTop: 2 }}>{label}</div>
    </div>
  );
}

export function ResultStat({ label, value, color, big }: { label: string; value: string; color?: string; big?: boolean }) {
  return (
    <div style={{ flex: 1, padding: "11px 13px", borderRadius: 11, background: "var(--inset)", border: "1px solid var(--stroke)" }}>
      <div className="mono display" style={{ fontSize: big ? 20 : 16, fontWeight: 700, color: color || "var(--t-hi)" }}>{value}</div>
      <div className="label-xs" style={{ fontSize: 8.5, marginTop: 3 }}>{label}</div>
    </div>
  );
}

export function Legend({ c, label }: { c: string; label: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
      <span style={{ width: 14, height: 3, borderRadius: 2, background: c, boxShadow: `0 0 6px ${c}` }} />
      <span style={{ fontSize: 11, color: "var(--t-mid)" }}>{label}</span>
    </div>
  );
}

/** Shared navigation target ids — single source of truth for routing within the SPA. */
export type PageId = "command" | "signals" | "backtest" | "sources" | "indicators";

/** Callbacks the shell hands down to pages/cards (modals + navigation). */
export interface ShellActions {
  onNav: (p: PageId) => void;
  onOpenAgent: (agentId: string) => void;
  onOpenContext: (trackerName: string) => void;
  onNewTracker: () => void;
  onRunBacktest: (themeName?: string) => void;
}
