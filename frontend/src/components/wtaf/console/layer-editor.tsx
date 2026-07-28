"use client";
/* ============ WTAF — one editable prompt layer (soul / rules / model / voice / skill) ============ */
import type { PromptView } from "@/lib/api/wtaf";

export type Busy = "save" | "reset" | undefined;

/**
 * Everything the console's layer editors need, owned once by the page.
 * Passing this down keeps every layer — a soul, a framework, a task prompt —
 * on the same save/reset/dirty behaviour.
 */
export interface LayerCtl {
  prompts: Record<string, PromptView>;
  drafts: Record<string, string>;
  busy: Record<string, Busy>;
  notice: Record<string, string>;
  /** No live backend (USE_MOCK / offline) — render, but don't pretend edits stick. */
  readOnly: boolean;
  setDraft: (key: string, text: string) => void;
  save: (key: string) => void;
  reset: (key: string) => void;
}

/** Accent colour per layer, so a section reads the same in the roster, editor and preview. */
export const LAYER_TONE: Record<string, string> = {
  soul: "var(--blue-bright)",
  rules: "var(--down)",
  mental_model: "var(--orange-bright)",
  personality: "var(--amber)",
  skill: "var(--indigo)",
};

export function LayerBadge({ layer, label }: { layer: string; label?: string }) {
  const tone = LAYER_TONE[layer] ?? "var(--t-lo)";
  return (
    <span
      className="chip mono"
      style={{
        fontSize: 9.5,
        color: tone,
        borderColor: `color-mix(in oklch, ${tone} 40%, transparent)`,
      }}
    >
      {label ?? layer.replace("_", " ")}
    </span>
  );
}

export function LayerEditor({
  ctl,
  promptKey,
  rows = 8,
  hint,
}: {
  ctl: LayerCtl;
  promptKey: string;
  rows?: number;
  hint?: string;
}) {
  const p = ctl.prompts[promptKey];
  if (!p) {
    return (
      <div className="mono" style={{ fontSize: 11, color: "var(--t-faint)" }}>
        {promptKey} · unavailable
      </div>
    );
  }

  const draft = ctl.drafts[promptKey] ?? p.current_text;
  const dirty = draft !== p.current_text;
  const b = ctl.busy[promptKey];
  const locked = ctl.readOnly || !!b;
  const tone = LAYER_TONE[p.layer] ?? "var(--t-lo)";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>{p.label}</span>
        <span className="mono" style={{ fontSize: 10, color: "var(--t-faint)" }}>
          {p.key}
        </span>
        {p.is_overridden && (
          <span
            className="chip"
            style={{
              fontSize: 9.5,
              color: "var(--amber)",
              borderColor: "color-mix(in oklch, var(--amber) 40%, transparent)",
            }}
          >
            customized
          </span>
        )}
      </div>

      <div style={{ fontSize: 11.5, color: "var(--t-lo)", lineHeight: 1.45 }}>
        {hint ?? p.description}
      </div>

      {p.placeholders.length > 0 && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
          <span className="mono" style={{ fontSize: 10.5, color: "var(--t-faint)" }}>
            placeholders:
          </span>
          {p.placeholders.map((ph) => (
            <span key={ph} className="chip mono" style={{ fontSize: 10.5 }}>
              {"{" + ph + "}"}
            </span>
          ))}
        </div>
      )}

      <textarea
        className="mono"
        value={draft}
        onChange={(e) => ctl.setDraft(promptKey, e.target.value)}
        spellCheck={false}
        rows={rows}
        readOnly={ctl.readOnly}
        style={{
          width: "100%",
          resize: "vertical",
          borderRadius: 9,
          padding: "10px 12px",
          fontSize: 12,
          lineHeight: 1.55,
          background: "var(--panel-2)",
          borderTop: "1px solid " + (dirty ? "var(--stroke-hi)" : "var(--stroke)"),
          borderRight: "1px solid " + (dirty ? "var(--stroke-hi)" : "var(--stroke)"),
          borderBottom: "1px solid " + (dirty ? "var(--stroke-hi)" : "var(--stroke)"),
          borderLeft: `2px solid ${tone}`,
          color: "var(--t-hi)",
          outline: "none",
          opacity: ctl.readOnly ? 0.65 : 1,
        }}
      />

      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <button
          type="button"
          onClick={() => ctl.save(promptKey)}
          disabled={!dirty || locked}
          style={{
            padding: "7px 15px",
            borderRadius: 9,
            fontSize: 12.5,
            fontWeight: 600,
            border: "1px solid color-mix(in oklch, var(--blue-bright) 45%, transparent)",
            background: "color-mix(in oklch, var(--blue-bright) 16%, transparent)",
            color: "var(--blue-bright)",
            opacity: !dirty || locked ? 0.4 : 1,
            cursor: !dirty || locked ? "default" : "pointer",
          }}
        >
          {b === "save" ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={() => ctl.reset(promptKey)}
          disabled={!p.is_overridden || locked}
          style={{
            padding: "7px 15px",
            borderRadius: 9,
            fontSize: 12.5,
            background: "var(--panel-2)",
            border: "1px solid var(--stroke)",
            color: "var(--t-mid)",
            opacity: !p.is_overridden || locked ? 0.4 : 1,
            cursor: !p.is_overridden || locked ? "default" : "pointer",
          }}
        >
          {b === "reset" ? "Resetting…" : "Reset to default"}
        </button>
        <span
          className="mono"
          style={{
            fontSize: 10.5,
            color: ctl.notice[promptKey]?.includes("failed") ? "var(--down)" : "var(--t-lo)",
            marginLeft: "auto",
          }}
        >
          {b ? "" : ctl.notice[promptKey] || (dirty ? "unsaved changes" : "")}
        </span>
      </div>
    </div>
  );
}
