"use client";
import Link from "next/link";
import type { Tracker } from "@/lib/types";
import { STANCE_COLOR } from "@/lib/stance";
import { Card, EmptyState } from "../primitives";

export function TrackersCard({
  trackers,
  onOpenContext,
  discovering = false,
}: {
  trackers: Tracker[];
  onOpenContext: (trackerName: string) => void;
  discovering?: boolean;
}) {
  const isEmpty = trackers.length === 0;
  return (
    <Card title="Concept Trackers" sub={`${trackers.length}/15 active · Winston's read`} className="span7"
      loading={discovering && isEmpty} updating={discovering && !isEmpty}
      action={<Link href="/signals" style={{ fontSize: 11, color: "var(--blue-bright)" }}>Open terminal →</Link>}>
      {trackers.length === 0 ? (
        <EmptyState label="No concept trackers yet" sub="Run a discovery to surface themes" />
      ) : (
      <div style={{ display: "flex", flexDirection: "column" }}>
        {/* Stance and its one-liner are Winston's graded read on the fixed theme taxonomy
            (backend council/theme_reads.py) — deliberately not `tone`/`spark`, which count
            mentions and so say how loud a theme is, never which way. The volume charts
            still live on the Signal Terminal, where that is the point. */}
        {trackers.map((t, i) => (
          <button key={i} onClick={() => onOpenContext(t.name)} style={{ display: "flex", alignItems: "center", gap: 12, padding: "9px 8px", margin: "0 -8px", background: "transparent", border: "none", borderBottom: i < trackers.length - 1 ? "1px solid var(--stroke)" : "none", textAlign: "left", borderRadius: 8, transition: "background .15s" }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "var(--panel-2)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
            <span style={{ fontSize: 12.5, fontWeight: 500, flex: "0 0 30%", lineHeight: 1.35, textWrap: "pretty", color: "var(--t-hi)" }}>{t.name}</span>
            <div style={{ flex: 1, minWidth: 0, fontSize: 11.5, lineHeight: 1.4, textWrap: "pretty", color: t.rationale ? "var(--t-lo)" : "var(--t-faint)" }}>
              {t.rationale || "Nothing in the corpus reads on this yet."}
            </div>
            <span className="mono" style={{ fontSize: 12, width: 38, textAlign: "right", flexShrink: 0, color: "var(--t-mid)" }}>{t.mentions}</span>
            <span className="mono" style={{ fontSize: 10, width: 48, textAlign: "right", flexShrink: 0, color: "var(--t-faint)" }}>{t.channels} ch</span>
            <span className="chip" style={{ flexShrink: 0, color: STANCE_COLOR[t.stance], borderColor: `color-mix(in oklch, ${STANCE_COLOR[t.stance]} 40%, transparent)` }}>{t.stance}</span>
          </button>
        ))}
      </div>
      )}
    </Card>
  );
}
