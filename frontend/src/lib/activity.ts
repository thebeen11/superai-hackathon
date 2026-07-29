/**
 * Maps the backend's streamed SSE progress frames onto the 10 council agents, so the
 * UI can show what each agent is *currently* doing. This is the single source of truth
 * for stage → agent routing; the provider's `handleProgress` and any consumer reuse it.
 *
 * Backend stages (see backend/app/* emit calls):
 *   refine, discover*         → Wilfred (Tier 1, sub-routed by data.source_type)
 *   dataeng, dataeng.item     → Timo    (Tier 2)
 *   council                   → orchestrator-wide (unrouted, "Council")
 *   council.analyst (data.desk)→ Andie  (Tier 3 desk)
 *   council.debate            → Freddy  (Tier 4, Bull/Bear from message)
 *   council.macro             → Macro Analyst (macro bypass, sits with Tier 5)
 *   council.chairman          → Winston (Tier 5)
 */
import type { ActivityEntry, AgentStatus, LiveAgentStatus, Tier } from "./types";
import type { ProgressEvent } from "./api/sse";

interface Routed {
  agentId: string | null;
  agentName: string;
  tierKey: Tier["key"] | null;
}

/** Tier keys whose agents *reason* (LLM) — shown as "thinking" while in-flight. */
const REASONING_TIERS = new Set<Tier["key"]>(["analysts", "debate", "chairman"]);

const ANDIE_BY_DESK: Record<string, { id: string; name: string }> = {
  TMT: { id: "andie-tech", name: "Andie-TMT" },
  Physical: { id: "andie-physical", name: "Andie-Physical" },
  Capital: { id: "andie-capital", name: "Andie-Capital" },
};

/** Route one progress event to the agent (and tier) responsible for it. */
export function routeEvent(evt: ProgressEvent): Routed {
  const { stage, data, message } = evt;

  if (stage === "refine" || stage.startsWith("discover")) {
    // Per-source events use a dotted stage (`discover.youtube` / `discover.web`); the
    // rare skip-on-error event instead carries `source_type`. Route on either.
    const src = typeof data.source_type === "string" ? data.source_type : "";
    if (stage === "discover.youtube" || src === "youtube") return { agentId: "wilfred-video", agentName: "Wilfred-Video", tierKey: "discovery" };
    if (stage === "discover.web" || src === "web") return { agentId: "wilfred-news", agentName: "Wilfred-News", tierKey: "discovery" };
    return { agentId: null, agentName: "Wilfred", tierKey: "discovery" };
  }

  if (stage === "dataeng" || stage === "dataeng.item") {
    return { agentId: "timo", agentName: "Timo", tierKey: "routing" };
  }

  if (stage === "council.analyst") {
    const desk = typeof data.desk === "string" ? ANDIE_BY_DESK[data.desk] : undefined;
    if (desk) return { agentId: desk.id, agentName: desk.name, tierKey: "analysts" };
    return { agentId: null, agentName: "Andie", tierKey: "analysts" };
  }

  if (stage === "council.debate") {
    if (/\bBull\b/i.test(message)) return { agentId: "freddy-bull", agentName: "Freddy-Bull", tierKey: "debate" };
    if (/\bBear\b/i.test(message)) return { agentId: "freddy-bear", agentName: "Freddy-Bear", tierKey: "debate" };
    return { agentId: null, agentName: "Freddy", tierKey: "debate" };
  }

  if (stage === "council.macro") {
    return { agentId: "macro-analyst", agentName: "Macro Analyst", tierKey: "chairman" };
  }

  if (stage === "council.chairman") {
    return { agentId: "winston", agentName: "Winston", tierKey: "chairman" };
  }

  // Orchestrator-level (`council`) and anything unrecognised → unrouted council line.
  return { agentId: null, agentName: "Council", tierKey: null };
}

/** Strip the `[n/m]` counter prefix some messages carry (e.g. dataeng.item). */
function cleanMessage(message: string): string {
  return message.replace(/^\[\d+\/\d+\]\s*/, "");
}

/** Turn a progress event into a log entry. `seq` makes the React key stable & unique. */
export function toEntry(evt: ProgressEvent, seq: number): ActivityEntry {
  const r = routeEvent(evt);
  const ts = typeof evt.ts === "number" ? evt.ts : Date.now() / 1000;
  return {
    id: `${ts}-${seq}`,
    ts,
    agentId: r.agentId,
    agentName: r.agentName,
    tierKey: r.tierKey,
    message: cleanMessage(evt.message) || evt.stage,
    status: evt.status,
    stage: evt.stage,
  };
}

/**
 * Derive a live status for the routed agent: terminal (ok/skip/error) → idle, otherwise
 * in-flight → "thinking" for reasoning tiers, "active" for ingestion tiers.
 */
export function toLiveStatus(evt: ProgressEvent): LiveAgentStatus | null {
  const r = routeEvent(evt);
  if (!r.agentId) return null; // only concrete agents get a live dot override
  const terminal = evt.status === "ok" || evt.status === "skip" || evt.status === "error";
  const status: AgentStatus = terminal ? "idle" : REASONING_TIERS.has(r.tierKey!) ? "thinking" : "active";
  return { status, statusText: cleanMessage(evt.message) || evt.stage };
}
