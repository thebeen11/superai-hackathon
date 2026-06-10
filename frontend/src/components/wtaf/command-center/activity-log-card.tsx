"use client";
/* ============ WTAF — live agent activity feed ============ */
import { useEffect, useRef } from "react";
import type { AccentKey, ActivityEntry, Tier } from "@/lib/types";
import { useWtaf } from "@/providers/wtaf-provider";
import { ACCENTS } from "../accents";
import { Card, Dot, EmptyState } from "../primitives";

/** Tier → accent for the agent-name chip. */
const TIER_ACCENT: Record<NonNullable<Tier["key"]>, AccentKey> = {
  discovery: "blue",
  routing: "indigo",
  analysts: "orange",
  debate: "amber",
  chairman: "chair",
};

function clock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("en-GB", { hour12: false });
}

function Row({ e }: { e: ActivityEntry }) {
  const accent = e.tierKey ? TIER_ACCENT[e.tierKey] : "indigo";
  const ac = ACCENTS[accent] ?? ACCENTS.blue;
  const color =
    e.status === "error" || e.status === "skip" ? "var(--down)"
    : e.status === "ok" ? "var(--up)"
    : "var(--t-mid)";
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: 9, padding: "5px 0" }}>
      <span className="mono" style={{ fontSize: 10, color: "var(--t-faint)", flexShrink: 0 }}>{clock(e.ts)}</span>
      <span className="mono" style={{
        fontSize: 9.5, fontWeight: 600, flexShrink: 0, padding: "1px 6px", borderRadius: 6, whiteSpace: "nowrap",
        color: ac.c, background: `color-mix(in oklch, ${ac.c} 14%, transparent)`, border: `1px solid color-mix(in oklch, ${ac.c} 35%, transparent)`,
      }}>{e.agentName}</span>
      <span className="mono" style={{ fontSize: 11, color, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.message}</span>
    </div>
  );
}

export function ActivityLogCard() {
  const { activity, discovering } = useWtaf();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Keep the newest line in view as the feed streams.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [activity.length]);

  return (
    <Card
      title="Activity Log"
      sub={activity.length ? `${activity.length} events` : "live agent feed"}
      className="span4"
      action={
        discovering ? (
          <span className="mono" style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 10.5, color: "var(--amber)" }}>
            <Dot tone="orange" /> streaming
          </span>
        ) : undefined
      }
    >
      {activity.length === 0 ? (
        <EmptyState label="No recent agent activity" sub="Run a discovery to watch the council work" minHeight={140} />
      ) : (
        <div ref={scrollRef} style={{ maxHeight: 320, overflowY: "auto", display: "flex", flexDirection: "column" }}>
          {activity.map((e) => (<Row key={e.id} e={e} />))}
        </div>
      )}
    </Card>
  );
}
