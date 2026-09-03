"use client";
import type { Debate, Tier } from "@/lib/types";
import { Card, EmptyState } from "../primitives";
import { AgentAvatar } from "../agents";

/** True once the chamber has actually sat — otherwise the card shows its empty state. */
export function hasDebated(debate: Debate): boolean {
  return debate.transcript.length > 0 || debate.verdict !== "";
}

/**
 * The chamber itself: round progress, the two stances, Winston's verdict.
 *
 * Split out from the card around it because the same transcript is rendered in two
 * places on different clocks — the council-wide debate on the Command Center, and a
 * single-ticker debate on a ticker page, which owns its own header, run picker and
 * trigger. Only the frame differs; a Bull/Bear exchange should read identically in both.
 */
export function DebateChamber({
  debate,
  tiers,
  onOpenTranscript,
}: {
  debate: Debate;
  tiers: Tier[];
  onOpenTranscript: () => void;
}) {
  const db = debate;
  const debateTier = tiers.find((t) => t.key === "debate")!;
  const bull = debateTier.squad[0];
  const bear = debateTier.squad[1];
  const winston = tiers.find((t) => t.key === "chairman")!.squad[0];
  const sides = [
    { ag: bull, side: db.bull, c: "var(--up)" },
    { ag: bear, side: db.bear, c: "var(--down)" },
  ];
  return (
    <>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 11,
        }}
      >
        <span className="chip" style={{ fontSize: 9.5 }}>
          {db.topic}
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
          {Array.from({ length: db.rounds }).map((_, i) => (
            <span
              key={i}
              style={{
                width: 18,
                height: 4,
                borderRadius: 99,
                background:
                  i < db.round ? "var(--blue-bright)" : "rgba(255,255,255,0.1)",
                boxShadow: i < db.round ? "0 0 6px var(--blue)" : "none",
              }}
            />
          ))}
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
        {sides.map(({ ag, side, c }, i) => (
          <div
            key={i}
            style={{
              padding: "11px 12px",
              borderRadius: 11,
              background: "var(--inset)",
              border: "1px solid var(--stroke)",
              borderTop: `2px solid ${c}`,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 7,
              }}
            >
              <AgentAvatar a={ag} size={24} />
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: c }}>
                  {side.name.split("-")[1]}
                </div>
                <div
                  className="mono"
                  style={{ fontSize: 9, color: "var(--t-faint)" }}
                >
                  {side.model}
                </div>
              </div>
            </div>
            <p
              style={{
                fontSize: 11,
                lineHeight: 1.45,
                color: "var(--t-mid)",
                textWrap: "pretty",
              }}
            >
              {side.stance}
            </p>
          </div>
        ))}
      </div>
      <button
        onClick={onOpenTranscript}
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 9,
          width: "100%",
          textAlign: "left",
          marginTop: 10,
          padding: "10px 12px",
          borderRadius: 11,
          background: "color-mix(in oklch, var(--indigo) 9%, var(--inset))",
          border:
            "1px solid color-mix(in oklch, var(--indigo) 32%, transparent)",
        }}
      >
        <AgentAvatar a={winston} size={24} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            className="label-xs"
            style={{
              fontSize: 8,
              color: "oklch(0.86 0.05 250)",
              marginBottom: 2,
            }}
          >
            Winston · verdict
          </div>
          <div
            style={{
              fontSize: 11,
              lineHeight: 1.4,
              color: "var(--t-hi)",
              textWrap: "pretty",
            }}
          >
            {db.verdict}
          </div>
        </div>
      </button>
    </>
  );
}

/** The Command Center's chamber — the council-wide debate off the nightly snapshot. */
export function DebateCard({
  debate,
  tiers,
  onOpenDebate,
}: {
  debate: Debate;
  tiers: Tier[];
  onOpenDebate: () => void;
}) {
  const db = debate;
  if (!hasDebated(db)) {
    return (
      <Card
        title="Debate Chamber"
        sub="adversarial · Bull vs Bear"
        className="span8"
      >
        <EmptyState
          label="No debate yet"
          sub="Awaiting Tier 4 · Freddy (Bull vs Bear)"
          minHeight={180}
        />
      </Card>
    );
  }
  return (
    <Card
      title="Debate Chamber"
      sub={`round ${db.round} / ${db.rounds}`}
      className="span8"
      action={
        <button
          onClick={onOpenDebate}
          style={{
            fontSize: 11,
            color: "var(--blue-bright)",
            background: "none",
            border: "none",
          }}
        >
          View transcript →
        </button>
      }
    >
      <DebateChamber debate={db} tiers={tiers} onOpenTranscript={onOpenDebate} />
    </Card>
  );
}
