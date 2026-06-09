"use client";
/* Tier 4 — Bull vs Bear debate transcript (adversarial reasoning). */
import type { Debate } from "@/lib/types";

export function DebateModal({ debate, onClose }: { debate: Debate; onClose: () => void }) {
  const db = debate;
  const sideC: Record<string, string> = { bull: "var(--up)", bear: "var(--down)", winston: "oklch(0.88 0.05 250)" };
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 72, background: "rgba(5,7,12,0.62)", backdropFilter: "blur(4px)", display: "grid", placeItems: "center", padding: 24, animation: "rise .18s" }}>
      <div onClick={(e) => e.stopPropagation()} className="card" style={{ width: 620, maxWidth: "94vw", maxHeight: "90vh", overflowY: "auto", animation: "rise .26s" }}>
        <div className="card-pad">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
            <div>
              <div className="label-xs" style={{ marginBottom: 5 }}>Tier 4 · Debate Chamber · adversarial reasoning</div>
              <h3 className="display" style={{ fontSize: 18, fontWeight: 600 }}>{db.topic}</h3>
            </div>
            <button onClick={onClose} style={{ background: "var(--panel-2)", border: "1px solid var(--stroke)", borderRadius: 8, width: 28, height: 28, color: "var(--t-mid)" }}>×</button>
          </div>
          <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
            <span className="chip" style={{ color: "var(--up)", borderColor: "color-mix(in oklch, var(--up) 40%, transparent)" }}>Bull · {db.bull.model}</span>
            <span className="chip" style={{ color: "var(--down)", borderColor: "color-mix(in oklch, var(--down) 40%, transparent)" }}>Bear · {db.bear.model}</span>
            <span className="chip">{db.rounds} rounds</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {db.transcript.map((m, i) => {
              const c = sideC[m.who];
              const isW = m.who === "winston";
              return (
                <div key={i} style={{ display: "flex", gap: 11, padding: "12px 14px", borderRadius: 11, background: isW ? "color-mix(in oklch, var(--indigo) 9%, var(--inset))" : "var(--inset)", border: "1px solid " + (isW ? "color-mix(in oklch, var(--indigo) 35%, transparent)" : "var(--stroke)"), borderLeft: `2px solid ${c}` }}>
                  <div style={{ flexShrink: 0, width: 54 }}>
                    <div className="mono" style={{ fontSize: 10.5, fontWeight: 700, color: c }}>{m.round}</div>
                    <div className="label-xs" style={{ fontSize: 8, marginTop: 2 }}>{m.label.split(" · ")[0]}</div>
                  </div>
                  <p style={{ fontSize: 12.5, lineHeight: 1.5, color: "var(--t-mid)", textWrap: "pretty", flex: 1 }}>{m.text}</p>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
