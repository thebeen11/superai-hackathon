"use client";
/* ============ WTAF — console roster: the council, grouped by tier ============ */
import type { AccentKey } from "@/lib/types";
import type { AgentView } from "@/lib/api/wtaf";
import { AgentAvatar } from "../agents";

/** Sentinel selection for the council-wide soul + rules. */
export const GLOBAL_ID = "__global__";

function Row({
  glyph,
  accent,
  name,
  sub,
  selected,
  onClick,
}: {
  glyph: string;
  accent: AccentKey;
  name: string;
  sub: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        width: "100%",
        textAlign: "left",
        padding: "8px 9px",
        borderRadius: 10,
        border: "1px solid " + (selected ? "var(--stroke-hi)" : "transparent"),
        background: selected ? "var(--panel-2)" : "transparent",
        cursor: "pointer",
      }}
    >
      <AgentAvatar a={{ glyph, accent }} size={28} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 12.5,
            fontWeight: 600,
            color: selected ? "var(--t-hi)" : "var(--t-mid)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {name}
        </div>
        <div
          className="mono"
          style={{
            fontSize: 9.5,
            color: "var(--t-faint)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          {sub}
        </div>
      </div>
    </button>
  );
}

export function AgentRoster({
  agents,
  selectedId,
  customizedGlobals,
  onSelect,
}: {
  agents: AgentView[];
  selectedId: string;
  /** How many of soul/rules carry an override — surfaced on the Global row. */
  customizedGlobals: number;
  onSelect: (id: string) => void;
}) {
  // Group by tier, preserving the backend's council order.
  const tiers: { tier: number; label: string; rows: AgentView[] }[] = [];
  for (const a of agents) {
    const last = tiers[tiers.length - 1];
    if (last && last.tier === a.tier) last.rows.push(a);
    else tiers.push({ tier: a.tier, label: a.tier_label, rows: [a] });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div>
        <div className="label-xs" style={{ marginBottom: 7 }}>
          Council-wide
        </div>
        <Row
          glyph="§"
          accent="chair"
          name="Soul & Rules"
          sub={customizedGlobals ? `${customizedGlobals} customized` : "inherited by all"}
          selected={selectedId === GLOBAL_ID}
          onClick={() => onSelect(GLOBAL_ID)}
        />
      </div>

      {tiers.map((t) => (
        <div key={t.tier}>
          <div className="label-xs" style={{ marginBottom: 7 }}>
            T{t.tier} · {t.label}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {t.rows.map((a) => (
              <Row
                key={a.id}
                glyph={a.glyph}
                accent={a.accent as AccentKey}
                name={a.name}
                sub={`${a.mental_models.length} models · ${a.skill_keys.length} skills`}
                selected={selectedId === a.id}
                onClick={() => onSelect(a.id)}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
