"use client";
/* ============ WTAF — agent council ============ */
import type { ReactNode } from "react";
import type { ActivityEntry, Agent, LiveAgentStatus, PipelineStage, Tier } from "@/lib/types";
import { ACCENTS, STATE_TONE } from "./accents";
import { Dot } from "./primitives";

export function AgentAvatar({ a, size = 34 }: { a: Agent; size?: number }) {
  const ac = ACCENTS[a.accent] || ACCENTS.blue;
  const txt = a.accent === "chair" ? "#16181f" : "#fff";
  const glyphLen = (a.glyph || "").length;
  return (
    <div style={{
      width: size, height: size, borderRadius: 10, display: "grid", placeItems: "center", flexShrink: 0,
      fontFamily: "var(--font-display)", fontWeight: 700, fontSize: size * (glyphLen > 1 ? 0.34 : 0.44), color: txt,
      background: `linear-gradient(150deg, ${ac.g}, ${ac.c})`,
      boxShadow: `0 0 16px -4px ${ac.c}, inset 0 1px 0 rgba(255,255,255,0.3)`,
    }}>
      {a.glyph}
    </div>
  );
}

/* compact agent row used in the council card */
export function AgentRow({ a, onClick }: { a: Agent; onClick?: () => void }) {
  const tone = STATE_TONE[a.status] || "blue";
  return (
    <button onClick={onClick} style={{ display: "flex", alignItems: "center", gap: 11, width: "100%", textAlign: "left", background: "transparent", border: "none", padding: "9px 8px", borderRadius: 10, transition: "background .15s" }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--panel-2)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
      <AgentAvatar a={a} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <span style={{ fontSize: 13.5, fontWeight: 600 }}>{a.name}</span>
          <span className="label-xs" style={{ fontSize: 9 }}>{a.role.split(" · ")[0]}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
          <Dot tone={tone} pulse={a.status !== "idle"} />
          <span className="mono" style={{ fontSize: 11, color: "var(--t-mid)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.statusText}</span>
        </div>
      </div>
      <div style={{ textAlign: "right" }}>
        <div className="mono" style={{ fontSize: 13, fontWeight: 600, color: a.queue ? "var(--t-hi)" : "var(--t-lo)" }}>{a.queue}</div>
        <div className="label-xs" style={{ fontSize: 8.5 }}>queue</div>
      </div>
    </button>
  );
}

/* the pipeline flow strip */
export function PipelineFlow({ pipeline }: { pipeline: PipelineStage[] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
      {pipeline.map((p, i) => {
        const tone = STATE_TONE[p.state];
        const ac = ACCENTS[tone];
        return (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 11 }}>
            <div style={{
              width: 22, height: 22, borderRadius: 7, display: "grid", placeItems: "center", flexShrink: 0,
              border: `1px solid ${p.state === "pending" ? "var(--stroke)" : ac.c}`,
              background: p.state === "pending" ? "transparent" : `color-mix(in oklch, ${ac.c} 15%, transparent)`,
              color: p.state === "pending" ? "var(--t-lo)" : ac.c,
            }}>
              {p.state === "done" ? (
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.2"><path d="M20 6L9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" /></svg>
              ) : p.state === "progress" ? (
                <span style={{ width: 9, height: 9, borderRadius: 99, border: `2px solid ${ac.c}`, borderTopColor: "transparent", display: "block", animation: "spin 0.9s linear infinite" }} />
              ) : (
                <span style={{ width: 5, height: 5, borderRadius: 99, background: "var(--t-faint)" }} />
              )}
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12.5, fontWeight: 500, color: p.state === "pending" ? "var(--t-lo)" : "var(--t-hi)" }}>{p.stage}</div>
            </div>
            <span className="mono" style={{ fontSize: 11, color: "var(--t-lo)" }}>{p.detail}</span>
          </div>
        );
      })}
    </div>
  );
}

export function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div className="label-xs" style={{ marginBottom: 9 }}>{label}</div>
      {children}
    </div>
  );
}

/** Format an epoch-seconds timestamp as HH:MM:SS for the live activity log. */
function fmtClock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("en-GB", { hour12: false });
}

/* slide-in detail drawer */
export function AgentDrawer({
  agent,
  entries,
  live,
  onClose,
}: {
  agent: Agent | null;
  /** Live activity for this agent (overrides the static `agent.log` when present). */
  entries?: ActivityEntry[];
  /** Live status override for the header dot. */
  live?: LiveAgentStatus;
  onClose: () => void;
}) {
  if (!agent) return null;
  const ac = ACCENTS[agent.accent] || ACCENTS.blue;
  const status = live?.status ?? agent.status;
  const statusText = live?.statusText ?? agent.statusText;
  const tone = STATE_TONE[status];
  const liveEntries = entries ?? [];
  const hasLive = liveEntries.length > 0;
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 60, background: "rgba(5,7,12,0.55)", backdropFilter: "blur(3px)", display: "flex", justifyContent: "flex-end", animation: "rise .2s" }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 380, maxWidth: "92vw", height: "100%", background: "var(--bg-1)", borderLeft: "1px solid var(--stroke-hi)", boxShadow: "-30px 0 60px -20px rgba(0,0,0,0.7)", overflowY: "auto", padding: 22, animation: "rise .28s" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 13, marginBottom: 18 }}>
          <AgentAvatar a={agent} size={48} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 19, fontWeight: 600, fontFamily: "var(--font-display)" }}>{agent.name}</div>
            <div className="mono" style={{ fontSize: 11.5, color: "var(--t-mid)" }}>{agent.role}</div>
          </div>
          <button onClick={onClose} style={{ background: "var(--panel-2)", border: "1px solid var(--stroke)", borderRadius: 8, width: 30, height: 30, color: "var(--t-mid)", fontSize: 16 }}>×</button>
        </div>

        <div className="card card-pad" style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
          <Dot tone={tone} pulse={status !== "idle"} />
          <span style={{ fontSize: 13, fontWeight: 500 }}>{statusText}</span>
          <div style={{ marginLeft: "auto", display: "flex", gap: 16 }}>
            <div style={{ textAlign: "right" }}><div className="mono" style={{ fontSize: 15, fontWeight: 600 }}>{agent.queue}</div><div className="label-xs" style={{ fontSize: 8 }}>queue</div></div>
            <div style={{ textAlign: "right" }}><div className="mono" style={{ fontSize: 15, fontWeight: 600, color: ac.c }}>{agent.throughput}</div><div className="label-xs" style={{ fontSize: 8 }}>rate</div></div>
          </div>
        </div>

        <Section label="Skills">
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {agent.skills.map((s, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 12.5, color: "var(--t-mid)" }}>
                <span style={{ width: 5, height: 5, borderRadius: 99, background: ac.c, boxShadow: `0 0 6px ${ac.c}` }} />{s}
              </div>
            ))}
          </div>
        </Section>

        <Section label="Tools">
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {agent.tools.map((t, i) => (<span key={i} className="chip">{t}</span>))}
          </div>
        </Section>

        <Section label={hasLive ? "Activity log · live" : "Activity log"}>
          {hasLive ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
              {liveEntries.map((e, i) => {
                const etone = ACCENTS[STATE_TONE[e.status]] ? STATE_TONE[e.status] : null;
                const color =
                  e.status === "error" || e.status === "skip" ? "var(--down)"
                  : e.status === "ok" ? "var(--up)"
                  : "var(--t-mid)";
                return (
                  <div key={e.id} style={{ display: "flex", gap: 10, padding: "8px 0", borderBottom: i < liveEntries.length - 1 ? "1px solid var(--stroke)" : "none" }}>
                    <span className="mono" style={{ fontSize: 10.5, color: "var(--t-faint)", flexShrink: 0, paddingTop: 1 }}>{fmtClock(e.ts)}</span>
                    <span className="mono" style={{ fontSize: 11.5, color }}>{e.message}</span>
                    {etone && <span style={{ marginLeft: "auto", paddingTop: 4 }}><Dot tone={etone} pulse={false} /></span>}
                  </div>
                );
              })}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
              {agent.log.map((l, i) => (
                <div key={i} style={{ display: "flex", gap: 10, padding: "8px 0", borderBottom: i < agent.log.length - 1 ? "1px solid var(--stroke)" : "none" }}>
                  <span className="mono" style={{ fontSize: 10.5, color: "var(--t-faint)", flexShrink: 0, paddingTop: 1 }}>{String(i * 3 + 1).padStart(2, "0")}m</span>
                  <span className="mono" style={{ fontSize: 11.5, color: "var(--t-mid)" }}>{l}</span>
                </div>
              ))}
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}

/* ---- 5-tier squad flow (MapReduce fan-out → fan-in) ---- */
function SquadMember({ a, live, onOpenAgent }: { a: Agent; live?: LiveAgentStatus; onOpenAgent: (a: Agent) => void }) {
  const status = live?.status ?? a.status;
  const statusText = live?.statusText ?? a.statusText;
  const tone = STATE_TONE[status] || "blue";
  return (
    <button onClick={() => onOpenAgent(a)} title={a.name + " · " + statusText}
      style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 5, background: "transparent", border: "none", padding: 0 }}>
      <div style={{ position: "relative" }}>
        <AgentAvatar a={a} size={30} />
        <span style={{ position: "absolute", right: -2, bottom: -2, width: 9, height: 9, borderRadius: 99, background: ACCENTS[tone] ? ACCENTS[tone].c : tone, border: "2px solid var(--bg-1)", animation: status !== "idle" ? "pulse-dot 1.6s infinite" : "none" }} />
      </div>
      <span className="mono" style={{ fontSize: 9, color: "var(--t-lo)", whiteSpace: "nowrap" }}>{a.label}</span>
    </button>
  );
}

export function TierFlow({ tiers, onOpenAgent, liveStatus }: { tiers: Tier[]; onOpenAgent: (a: Agent) => void; liveStatus?: Record<string, LiveAgentStatus> }) {
  return (
    <div style={{ position: "relative", paddingRight: 30 }}>
      {/* macro bypass rail (Timo → Winston) lives in the reserved right gutter */}
      <div style={{ position: "absolute", right: 6, top: 62, bottom: 54, width: 20, pointerEvents: "none" }}>
        <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 0, borderRight: "1.5px dashed color-mix(in oklch, var(--indigo) 60%, transparent)" }} />
        <span style={{ position: "absolute", left: "50%", top: 0, transform: "translateX(-50%)", fontSize: 11, color: "var(--indigo)" }}>↗</span>
        <span style={{ position: "absolute", left: "50%", bottom: 0, transform: "translateX(-50%)", fontSize: 11, color: "var(--indigo)" }}>↘</span>
        <span className="label-xs" style={{ position: "absolute", left: "50%", top: "50%", transform: "translate(-50%,-50%) rotate(180deg)", writingMode: "vertical-rl", fontSize: 7.5, color: "var(--indigo)", letterSpacing: "0.1em", whiteSpace: "nowrap" }}>MACRO BYPASS</span>
      </div>

      {tiers.map((t, i) => {
        const ac = ACCENTS[t.accent] || ACCENTS.blue;
        // Derive the tier's live status from its squad: any non-idle live member drives
        // the tier dot; once members have reported but all are idle, the tier is done.
        const liveMembers = t.squad.map((a) => liveStatus?.[a.id]).filter(Boolean) as LiveAgentStatus[];
        const activeLive = liveMembers.find((l) => l.status !== "idle");
        const tStatus = activeLive ? activeLive.status : liveMembers.length ? "idle" : t.status;
        const tStatusText = activeLive ? activeLive.statusText : liveMembers.length ? "done" : t.statusText;
        const tone = STATE_TONE[tStatus] || "blue";
        return (
          <div key={t.key}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "7px 0" }}>
              <div style={{ width: 30, height: 30, borderRadius: 9, flexShrink: 0, display: "grid", placeItems: "center", background: `color-mix(in oklch, ${ac.c} 14%, transparent)`, border: `1px solid color-mix(in oklch, ${ac.c} 45%, transparent)` }}>
                <span className="mono" style={{ fontSize: 11, fontWeight: 700, color: t.accent === "chair" ? "var(--t-hi)" : ac.c }}>T{t.n}</span>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                  <span style={{ fontSize: 12.5, fontWeight: 600, whiteSpace: "nowrap" }}>{t.label}</span>
                  {t.squad.length > 1 && <span className="chip" style={{ fontSize: 8.5, padding: "1px 5px" }}>×{t.squad.length}</span>}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
                  <Dot tone={tone} pulse={tStatus !== "idle"} />
                  <span className="mono" style={{ fontSize: 10.5, color: "var(--t-lo)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{tStatusText}</span>
                </div>
              </div>
              <div style={{ display: "flex", gap: 10, flexShrink: 0, paddingRight: 4 }}>
                {t.squad.map((a) => (<SquadMember key={a.id} a={a} live={liveStatus?.[a.id]} onOpenAgent={onOpenAgent} />))}
              </div>
            </div>
            {i < tiers.length - 1 && (
              <div style={{ display: "flex", alignItems: "center", gap: 12, height: 14 }}>
                <div style={{ width: 30, display: "grid", placeItems: "center" }}>
                  <span style={{ width: 1.5, height: 14, background: "var(--stroke-hi)" }} />
                </div>
                <span className="mono" style={{ fontSize: 8.5, color: "var(--t-faint)", letterSpacing: "0.1em" }}>
                  {t.n === 1 ? "fan-in → route" : t.n === 2 ? "fan-out → desks" : t.n === 3 ? "→ debate" : "fan-in → judge"}</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
