"use client";
import Link from "next/link";
import type { Tracker } from "@/lib/types";
import { Card, Spark, EmptyState } from "../primitives";

export function TrackersCard({
  trackers,
  onOpenContext,
  discovering = false,
}: {
  trackers: Tracker[];
  onOpenContext: (trackerName: string) => void;
  discovering?: boolean;
}) {
  const toneC: Record<string, string> = { up: "var(--up)", down: "var(--down)", flat: "var(--t-lo)" };
  const isEmpty = trackers.length === 0;
  return (
    <Card title="Concept Trackers" sub={`${trackers.length}/15 active`} className="span7"
      loading={discovering && isEmpty} updating={discovering && !isEmpty}
      action={<Link href="/signals" style={{ fontSize: 11, color: "var(--blue-bright)" }}>Open terminal →</Link>}>
      {trackers.length === 0 ? (
        <EmptyState label="No concept trackers yet" sub="Run a discovery to surface themes" />
      ) : (
      <div style={{ display: "flex", flexDirection: "column" }}>
        {trackers.map((t, i) => (
          <button key={i} onClick={() => onOpenContext(t.name)} style={{ display: "flex", alignItems: "center", gap: 12, padding: "9px 8px", margin: "0 -8px", background: "transparent", border: "none", borderBottom: i < trackers.length - 1 ? "1px solid var(--stroke)" : "none", textAlign: "left", borderRadius: 8, transition: "background .15s" }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "var(--panel-2)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
            <span style={{ fontSize: 12.5, fontWeight: 500, flex: 1, color: "var(--t-hi)" }}>{t.name}</span>
            <div style={{ width: 84, height: 30, flexShrink: 0 }}><Spark data={t.spark} h={30} w={84} strokeW={1.8} animate={false} color={toneC[t.tone] === "var(--t-lo)" ? "var(--blue)" : toneC[t.tone]} /></div>
            <span className="mono" style={{ fontSize: 12, width: 38, textAlign: "right", color: "var(--t-mid)" }}>{t.mentions}</span>
            <span className="mono" style={{ fontSize: 11, width: 42, textAlign: "right", color: toneC[t.tone] }}>{t.chg >= 0 ? "+" : ""}{t.chg}</span>
            <span className="mono" style={{ fontSize: 10, width: 48, textAlign: "right", color: "var(--t-faint)" }}>{t.channels} ch</span>
          </button>
        ))}
      </div>
      )}
    </Card>
  );
}
