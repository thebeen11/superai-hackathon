"use client";
/* ============ WTAF — small shared building blocks ============ */
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

export function PageButton({ label, disabled, onClick }: { label: string; disabled: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled}
      style={{ padding: "8px 14px", borderRadius: 9, fontSize: 12.5, background: "var(--panel-2)", border: "1px solid var(--stroke)", color: "var(--t-mid)", opacity: disabled ? 0.4 : 1, cursor: disabled ? "default" : "pointer" }}>
      {label}
    </button>
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

/**
 * On/off pill for "is this thing being scanned" (watchlist tickers, YouTube channels).
 * Pattern mirrors the Agent Console mental-model switch.
 */
export function ScanToggle({ on, pending, onToggle, titleOn, titleOff }: {
  on: boolean;
  pending: boolean;
  onToggle: () => void;
  titleOn?: string;
  titleOff?: string;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={pending}
      aria-pressed={on}
      title={on ? (titleOn ?? "Scanning on — click to pause") : (titleOff ?? "Scanning paused — click to resume")}
      style={{
        width: 34, height: 19, borderRadius: 99, flexShrink: 0, position: "relative",
        border: "1px solid " + (on ? "color-mix(in oklch, var(--orange-bright) 55%, transparent)" : "var(--stroke-hi)"),
        background: on ? "color-mix(in oklch, var(--orange-bright) 26%, transparent)" : "var(--panel-2)",
        cursor: pending ? "default" : "pointer", opacity: pending ? 0.5 : 1, transition: "background .15s",
      }}
    >
      <span style={{ position: "absolute", top: 2, left: on ? 16 : 2, width: 13, height: 13, borderRadius: 99, background: on ? "var(--orange-bright)" : "var(--t-faint)", boxShadow: on ? "0 0 8px var(--orange-bright)" : "none", transition: "left .15s" }} />
    </button>
  );
}

/**
 * Row selection box for bulk actions. Native <input> so keyboard and a11y come for free;
 * `indeterminate` is DOM-only (no attribute), hence the ref.
 */
export function RowCheckbox({ checked, indeterminate, onChange, title, disabled }: {
  checked: boolean;
  indeterminate?: boolean;
  onChange: (next: boolean) => void;
  title: string;
  disabled?: boolean;
}) {
  return (
    <input
      type="checkbox"
      ref={(el) => { if (el) el.indeterminate = !!indeterminate && !checked; }}
      checked={checked}
      onChange={(e) => onChange(e.currentTarget.checked)}
      disabled={disabled}
      title={title}
      aria-label={title}
      style={{
        width: 14, height: 14, flexShrink: 0, margin: 0,
        accentColor: "var(--orange-bright)",
        cursor: disabled ? "default" : "pointer", opacity: disabled ? 0.4 : 1,
      }}
    />
  );
}

/** Small square glyph button for row actions (delete, confirm, refresh). */
export function IconButton({ children, title, onClick, disabled, danger }: {
  children: ReactNode;
  title: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{
        width: 26, height: 26, display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 13, lineHeight: 1, borderRadius: 7, flexShrink: 0,
        background: "var(--panel-2)", border: "1px solid " + (danger ? "color-mix(in oklch, var(--down) 45%, transparent)" : "var(--stroke)"),
        color: danger ? "var(--down)" : "var(--t-mid)",
        cursor: disabled ? "default" : "pointer", opacity: disabled ? 0.4 : 1, transition: "opacity .15s",
      }}
    >
      {children}
    </button>
  );
}

/** Overlay/drawer actions the shell exposes to pages/cards via `useShellActions()`. */
export interface ShellActions {
  onOpenAgent: (agentId: string) => void;
  onOpenContext: (trackerName: string) => void;
  onNewTracker: () => void;
  onOpenDebate: () => void;
}
