"use client";
import type { ThesisCountdown } from "@/lib/types";
import { Card, Ring } from "../primitives";
import { ACCENTS } from "../accents";
import type { PageId } from "../shared";

export function ThesisQuickCard({
  thesis,
  onNav,
  onNewTracker,
}: {
  thesis: ThesisCountdown;
  onNav: (p: PageId) => void;
  onNewTracker: () => void;
}) {
  const actions: { label: string; fn: () => void; tone: keyof typeof ACCENTS }[] = [
    { label: "New Tracker", fn: onNewTracker, tone: "blue" },
    { label: "Indicators", fn: () => onNav("indicators"), tone: "green" },
    { label: "Signals", fn: () => onNav("signals"), tone: "indigo" },
    { label: "Sources", fn: () => onNav("sources"), tone: "orange" },
  ];
  return (
    <Card title="Weekly Thesis" sub={thesis.target} className="span4">
      <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
        <Ring value={thesis.pct} size={104} stroke={9} from="orange" to="orange" track="rgba(255,255,255,0.07)">
          <div>
            <div className="mono display" style={{ fontSize: 17, fontWeight: 700 }}>{Math.round(thesis.pct * 100)}%</div>
            <div className="label-xs" style={{ fontSize: 7.5, marginTop: 2, color: "var(--orange-bright)" }}>ready</div>
          </div>
        </Ring>
        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7 }}>
          {actions.map((a, i) => (
            <button key={i} onClick={a.fn} style={{ padding: "9px 8px", borderRadius: 9, fontSize: 11.5, fontWeight: 500, background: "var(--panel-2)", border: "1px solid var(--stroke)", color: "var(--t-mid)", transition: "all .15s" }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = ACCENTS[a.tone].c; e.currentTarget.style.color = "var(--t-hi)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--stroke)"; e.currentTarget.style.color = "var(--t-mid)"; }}>
              {a.label}</button>
          ))}
        </div>
      </div>
    </Card>
  );
}
