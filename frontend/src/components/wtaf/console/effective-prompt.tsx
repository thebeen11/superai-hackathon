"use client";
/* ============ WTAF — console: the composed system prompt an agent actually sends ============ */
import { useEffect, useState } from "react";
import type { AgentView, EffectivePrompt } from "@/lib/api/wtaf";
import { getEffectivePrompt } from "@/lib/api/wtaf";
import { CardSkeleton, EmptyState } from "../primitives";
import { LAYER_TONE } from "./layer-editor";

/** Heading → layer key, so the preview is coloured like the editors it came from. */
function toneFor(heading: string): string {
  if (heading === "SOUL") return LAYER_TONE.soul;
  if (heading === "RULES") return LAYER_TONE.rules;
  if (heading === "MENTAL MODELS") return LAYER_TONE.mental_model;
  if (heading === "PERSONALITY") return LAYER_TONE.personality;
  if (heading.startsWith("TASK")) return LAYER_TONE.skill;
  return "var(--t-faint)";
}

export function EffectivePromptPanel({
  agent,
  /** Bumped after every save/toggle so the preview refetches. */
  version,
}: {
  agent: AgentView;
  version: number;
}) {
  const [picked, setPicked] = useState<string | null>(null);
  // Derive the shown skill so switching agents can't leave a stale selection behind.
  const skillKey =
    picked && agent.skill_keys.includes(picked) ? picked : (agent.skill_keys[0] ?? "");

  // One fetch per (agent, skill, edit) triple; the token is what makes a stale
  // response identifiable without clearing state inside the effect body.
  const token = `${agent.id}|${skillKey}|${version}`;
  const [result, setResult] = useState<{
    token: string;
    data?: EffectivePrompt;
    error?: string;
  } | null>(null);

  useEffect(() => {
    if (!skillKey) return;
    let alive = true;
    getEffectivePrompt(agent.id, skillKey)
      .then((d) => alive && setResult({ token, data: d }))
      .catch(
        (e) =>
          alive &&
          setResult({ token, error: (e as Error)?.message ?? "Failed to compose prompt" }),
      );
    return () => {
      alive = false;
    };
  }, [agent.id, skillKey, token]);

  const fresh = result?.token === token ? result : null;
  const data = fresh?.data ?? null;
  const error = fresh?.error ?? null;

  if (agent.skill_keys.length === 0) {
    return (
      <EmptyState
        label="No reasoning step"
        sub={`${agent.name} runs deterministic tools — no system prompt is sent.`}
      />
    );
  }

  const chars = data?.text.length ?? 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 9, flexWrap: "wrap" }}>
        <span style={{ fontSize: 11.5, color: "var(--t-lo)" }}>
          Exactly what Gemini receives on the next run:
        </span>
        {agent.skill_keys.map((k) => (
          <button
            key={k}
            type="button"
            onClick={() => setPicked(k)}
            className="mono"
            style={{
              fontSize: 10.5,
              padding: "4px 9px",
              borderRadius: 8,
              cursor: "pointer",
              background: k === skillKey ? "var(--panel-2)" : "transparent",
              border: "1px solid " + (k === skillKey ? "var(--stroke-hi)" : "var(--stroke)"),
              color: k === skillKey ? "var(--t-hi)" : "var(--t-lo)",
            }}
          >
            {k}
          </button>
        ))}
        {data && (
          <span className="mono" style={{ fontSize: 10, color: "var(--t-faint)", marginLeft: "auto" }}>
            {chars.toLocaleString()} chars · ≈{Math.round(chars / 4).toLocaleString()} tokens
          </span>
        )}
      </div>

      {error && <EmptyState label="Couldn't compose the prompt" sub={error} />}
      {!error && !data && <CardSkeleton rows={5} />}

      {data?.sections.map((s, i) => (
        <div
          key={i}
          style={{
            borderLeft: `2px solid ${toneFor(s.heading)}`,
            background: "var(--inset)",
            borderRadius: "0 10px 10px 0",
            padding: "10px 13px",
          }}
        >
          {s.heading && (
            <div
              className="label-xs"
              style={{ color: toneFor(s.heading), marginBottom: 6, fontSize: 9 }}
            >
              {s.heading}
            </div>
          )}
          <div
            className="mono"
            style={{
              fontSize: 11.5,
              lineHeight: 1.6,
              color: s.heading ? "var(--t-mid)" : "var(--t-faint)",
              whiteSpace: "pre-wrap",
            }}
          >
            {s.text}
          </div>
        </div>
      ))}

      {data && (
        <div className="mono" style={{ fontSize: 10, color: "var(--t-faint)" }}>
          Placeholders stay as literal tokens until the run fills them; the JSON output contract is
          appended by the reasoning wrapper after this text.
        </div>
      )}
    </div>
  );
}
