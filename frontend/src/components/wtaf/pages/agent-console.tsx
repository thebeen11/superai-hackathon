"use client";
/* ============ WTAF — Agent Console (edit the system prompts each agent runs on) ============ */
import { useEffect, useMemo, useState } from "react";
import { Card, EmptyState } from "../primitives";
import { PageHead } from "../shared";
import { USE_MOCK } from "@/lib/api/client";
import {
  getPrompts,
  savePrompt,
  resetPromptToDefault,
  type PromptView,
} from "@/lib/api/wtaf";

type Busy = "save" | "reset" | undefined;

export function AgentConsole() {
  const [prompts, setPrompts] = useState<PromptView[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<Record<string, Busy>>({});
  const [notice, setNotice] = useState<Record<string, string>>({});

  useEffect(() => {
    let alive = true;
    getPrompts()
      .then((rows) => {
        if (!alive) return;
        setPrompts(rows);
        setDrafts(Object.fromEntries(rows.map((p) => [p.key, p.current_text])));
      })
      .catch((e) => alive && setError(e?.message ?? "Failed to load prompts"));
    return () => {
      alive = false;
    };
  }, []);

  // Fold a returned PromptView back into local state (after save / reset).
  function apply(view: PromptView) {
    setPrompts((prev) =>
      (prev ?? []).map((p) => (p.key === view.key ? view : p)),
    );
    setDrafts((d) => ({ ...d, [view.key]: view.current_text }));
  }

  async function onSave(key: string) {
    setBusy((b) => ({ ...b, [key]: "save" }));
    setNotice((n) => ({ ...n, [key]: "" }));
    try {
      apply(await savePrompt(key, drafts[key] ?? ""));
      setNotice((n) => ({ ...n, [key]: "Saved · applies on next run" }));
    } catch (e) {
      setNotice((n) => ({ ...n, [key]: `Save failed: ${(e as Error)?.message ?? "error"}` }));
    } finally {
      setBusy((b) => ({ ...b, [key]: undefined }));
    }
  }

  async function onReset(key: string) {
    setBusy((b) => ({ ...b, [key]: "reset" }));
    setNotice((n) => ({ ...n, [key]: "" }));
    try {
      apply(await resetPromptToDefault(key));
      setNotice((n) => ({ ...n, [key]: "Reset to default" }));
    } catch (e) {
      setNotice((n) => ({ ...n, [key]: `Reset failed: ${(e as Error)?.message ?? "error"}` }));
    } finally {
      setBusy((b) => ({ ...b, [key]: undefined }));
    }
  }

  // Group prompts by their `group`, preserving first-seen order.
  const groups = useMemo(() => {
    const map = new Map<string, PromptView[]>();
    for (const p of prompts ?? []) {
      (map.get(p.group) ?? map.set(p.group, []).get(p.group)!).push(p);
    }
    return [...map.entries()];
  }, [prompts]);

  const overriddenCount = (prompts ?? []).filter((p) => p.is_overridden).length;

  return (
    <div>
      <PageHead
        title="Agent Console"
        sub={`edit the system prompts each agent runs on · ${overriddenCount} customized`}
      />

      {error && (
        <Card className="span12">
          <EmptyState label="Couldn't load prompts" sub={error} />
        </Card>
      )}

      {!error && USE_MOCK && (
        <Card className="span12">
          <EmptyState
            label="Live API not connected"
            sub="Set NEXT_PUBLIC_API_URL to your backend to edit prompts."
          />
        </Card>
      )}

      {!error && !USE_MOCK && prompts === null && (
        <Card className="span12" loading />
      )}

      {!error && prompts !== null && groups.length === 0 && !USE_MOCK && (
        <Card className="span12">
          <EmptyState label="No prompts found" sub="The backend returned an empty catalogue." />
        </Card>
      )}

      {groups.map(([group, rows]) => (
        <section key={group} style={{ marginBottom: 22 }}>
          <div className="label-xs" style={{ marginBottom: 10 }}>{group}</div>
          <div className="grid12">
            {rows.map((p) => {
              const draft = drafts[p.key] ?? "";
              const dirty = draft !== p.current_text;
              const b = busy[p.key];
              return (
                <Card
                  key={p.key}
                  className="span6"
                  title={p.label}
                  action={
                    p.is_overridden ? (
                      <span
                        className="chip"
                        style={{
                          color: "var(--amber)",
                          borderColor: "color-mix(in oklch, var(--amber) 40%, transparent)",
                        }}
                      >
                        customized
                      </span>
                    ) : (
                      <span className="chip" style={{ color: "var(--t-lo)" }}>default</span>
                    )
                  }
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <div style={{ fontSize: 11.5, color: "var(--t-lo)", lineHeight: 1.45 }}>
                      {p.description}
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
                      onChange={(e) =>
                        setDrafts((d) => ({ ...d, [p.key]: e.target.value }))
                      }
                      spellCheck={false}
                      rows={9}
                      style={{
                        width: "100%",
                        resize: "vertical",
                        borderRadius: 9,
                        padding: "10px 12px",
                        fontSize: 12,
                        lineHeight: 1.5,
                        background: "var(--panel-2)",
                        border: "1px solid " + (dirty ? "var(--stroke-hi)" : "var(--stroke)"),
                        color: "var(--t-hi)",
                        outline: "none",
                      }}
                    />

                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <button
                        type="button"
                        onClick={() => onSave(p.key)}
                        disabled={!dirty || !!b}
                        style={{
                          padding: "7px 15px",
                          borderRadius: 9,
                          fontSize: 12.5,
                          fontWeight: 600,
                          border: "1px solid color-mix(in oklch, var(--blue-bright) 45%, transparent)",
                          background: "color-mix(in oklch, var(--blue-bright) 16%, transparent)",
                          color: "var(--blue-bright)",
                          opacity: !dirty || b ? 0.4 : 1,
                          cursor: !dirty || b ? "default" : "pointer",
                        }}
                      >
                        {b === "save" ? "Saving…" : "Save"}
                      </button>
                      <button
                        type="button"
                        onClick={() => onReset(p.key)}
                        disabled={!p.is_overridden || !!b}
                        style={{
                          padding: "7px 15px",
                          borderRadius: 9,
                          fontSize: 12.5,
                          background: "var(--panel-2)",
                          border: "1px solid var(--stroke)",
                          color: "var(--t-mid)",
                          opacity: !p.is_overridden || b ? 0.4 : 1,
                          cursor: !p.is_overridden || b ? "default" : "pointer",
                        }}
                      >
                        {b === "reset" ? "Resetting…" : "Reset to default"}
                      </button>
                      <span
                        className="mono"
                        style={{
                          fontSize: 10.5,
                          color: notice[p.key]?.includes("failed")
                            ? "var(--down)"
                            : "var(--t-lo)",
                          marginLeft: "auto",
                        }}
                      >
                        {b ? "" : notice[p.key] || (dirty ? "unsaved changes" : "")}
                      </span>
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
