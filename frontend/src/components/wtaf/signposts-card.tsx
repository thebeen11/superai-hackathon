"use client";
/* ============ WTAF — Bear Market Signposts (Macro Analyst) ============ */
import type { Signpost, SignpostStatus, SourceDoc } from "@/lib/types";
import { useWtaf, useWtafData } from "@/providers/wtaf-provider";
import { Card, Ring, EmptyState } from "./primitives";
import { EvidenceList } from "./source-link";

/** Status → chip colour. An unevidenced row is greyed rather than shown as reassuring
 *  green: "nothing in the corpus spoke to it" is not the same claim as "we checked and
 *  it's clear". */
const STATUS_C: Record<SignpostStatus, string> = {
  Triggered: "var(--down)",
  Watch: "var(--amber)",
  Clear: "var(--up)",
};

function statusColor(s: Signpost): string {
  return s.evidenced ? STATUS_C[s.status] : "var(--t-faint)";
}

function SignpostRow({
  s,
  last,
  sources,
}: {
  s: Signpost;
  last: boolean;
  sources: SourceDoc[];
}) {
  const c = statusColor(s);
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 11,
        padding: "9px 0",
        borderBottom: last ? "none" : "1px solid var(--stroke)",
        opacity: s.evidenced ? 1 : 0.55,
      }}
    >
      <span
        className="chip mono"
        style={{
          fontSize: 10,
          flexShrink: 0,
          width: 74,
          textAlign: "center",
          color: c,
          borderColor: `color-mix(in oklch, ${c} 40%, transparent)`,
        }}
      >
        {s.evidenced ? s.status : "no data"}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--t-hi)" }}>{s.name}</div>
        {s.rationale && (
          <div style={{ fontSize: 11.5, color: "var(--t-lo)", marginTop: 3, lineHeight: 1.4, textWrap: "pretty" }}>
            {s.rationale}
          </div>
        )}
        <EvidenceList items={s.evidence} sources={sources} />
      </div>
    </div>
  );
}

export function SignpostsCard() {
  const d = useWtafData();
  const { discovering } = useWtaf();
  const sp = d.signposts;

  if (!sp) {
    return (
      <Card title="Bear Market Signposts" sub="fixed checklist · evidence-backed" className="span12" loading={discovering}>
        <EmptyState label="No signpost scan yet" sub="Run a discovery — the Macro Analyst grades the checklist off the macro stream" />
      </Card>
    );
  }

  // The ring reads as risk, so it fills red as more signposts light up.
  const hot = sp.riskScore >= 0.6;
  const mid = sp.riskScore >= 0.3;
  const half = Math.ceil(sp.signposts.length / 2);
  const columns = [sp.signposts.slice(0, half), sp.signposts.slice(half)];

  return (
    <Card
      title="Bear Market Signposts"
      sub={`${sp.triggered} of ${sp.total} triggered · ${sp.watch} on watch`}
      className="span12"
      updating={discovering}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 22, flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, flexShrink: 0, width: 178 }}>
          <Ring
            value={sp.riskScore}
            size={124}
            stroke={9}
            from={hot ? "orange" : mid ? "amber" : "green"}
            to={hot ? "red" : mid ? "orange" : "blue"}
          >
            <div>
              <div className="mono display" style={{ fontSize: 21, fontWeight: 700, color: hot ? "var(--down)" : mid ? "var(--amber)" : "var(--up)" }}>
                {sp.triggered}
                <span style={{ fontSize: 13, color: "var(--t-faint)" }}>/{sp.total}</span>
              </div>
              <div className="mono" style={{ fontSize: 9.5, color: "var(--t-faint)", marginTop: 2 }}>triggered</div>
            </div>
          </Ring>
          <div className="mono" style={{ fontSize: 10.5, textAlign: "center", color: hot ? "var(--down)" : mid ? "var(--amber)" : "var(--up)", letterSpacing: "0.04em" }}>
            {sp.label}
          </div>
          {sp.summary && (
            <div style={{ fontSize: 11.5, color: "var(--t-lo)", lineHeight: 1.45, textWrap: "pretty" }}>{sp.summary}</div>
          )}
        </div>

        <div style={{ flex: 1, minWidth: 280, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "0 22px" }}>
          {columns.map((col, ci) => (
            <div key={ci} style={{ display: "flex", flexDirection: "column" }}>
              {col.map((s, i) => (
                <SignpostRow key={s.key} s={s} last={i === col.length - 1} sources={d.sourceDocs} />
              ))}
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
