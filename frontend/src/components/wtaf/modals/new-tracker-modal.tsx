"use client";
import { useState } from "react";
import { useWtafData } from "@/providers/wtaf-provider";
import { Field } from "../shared";
import { Modal } from "./modal";

export function NewTrackerModal({ onClose }: { onClose: () => void }) {
  const d = useWtafData();
  const [mode, setMode] = useState("forward");
  const [chans, setChans] = useState<string[]>(["Silicon Signal", "Macro Lens"]);
  const allChans = d.sources.filter((s) => s.kind === "YouTube" || s.kind === "Podcast" || s.kind === "RSS").map((s) => s.name);
  const toggleChan = (c: string) => setChans((x) => (x.includes(c) ? x.filter((y) => y !== c) : [...x, c]));
  return (
    <Modal onClose={onClose} w={500}>
      <div className="card-pad">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 18 }}>
          <div>
            <div className="label-xs" style={{ marginBottom: 5 }}>New Concept Tracker</div>
            <h3 className="display" style={{ fontSize: 17, fontWeight: 600 }}>Track a meaning, not a string</h3>
          </div>
          <button onClick={onClose} style={{ background: "var(--panel-2)", border: "1px solid var(--stroke)", borderRadius: 8, width: 28, height: 28, color: "var(--t-mid)" }}>×</button>
        </div>
        <Field label="Concept / phrase">
          <input autoFocus placeholder="e.g. AI bubble collapse" className="r-input" defaultValue="" />
        </Field>
        <div className="mono" style={{ fontSize: 10.5, color: "var(--t-faint)", margin: "7px 0 16px" }}>semantic match · also catches &quot;tech valuations unsustainable&quot;</div>
        <Field label="Target channels">
          <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>
            {allChans.map((c) => (
              <button key={c} onClick={() => toggleChan(c)} style={{ padding: "6px 11px", borderRadius: 99, fontSize: 11.5, fontFamily: "var(--font-mono)", background: chans.includes(c) ? "color-mix(in oklch, var(--blue) 18%, transparent)" : "var(--panel-2)", border: "1px solid " + (chans.includes(c) ? "color-mix(in oklch, var(--blue) 45%, transparent)" : "var(--stroke)"), color: chans.includes(c) ? "var(--blue-bright)" : "var(--t-mid)" }}>{c}</button>
            ))}
          </div>
        </Field>
        <div style={{ marginTop: 16 }}>
          <Field label="Start mode">
            <div style={{ display: "flex", gap: 8 }}>
              {([["forward", "Track forward-only"], ["historical", "Run historically"]] as const).map(([v, l]) => (
                <button key={v} onClick={() => setMode(v)} style={{ flex: 1, padding: "11px", borderRadius: 10, fontSize: 12, fontWeight: 500, background: mode === v ? "color-mix(in oklch, var(--blue) 16%, transparent)" : "var(--panel-2)", border: "1px solid " + (mode === v ? "color-mix(in oklch, var(--blue) 45%, transparent)" : "var(--stroke)"), color: mode === v ? "var(--blue-bright)" : "var(--t-mid)" }}>{l}</button>
              ))}
            </div>
          </Field>
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--stroke)" }}>
          <span className="mono" style={{ fontSize: 10.5, color: "var(--t-lo)" }}>{d.trackers.length}/15 trackers used</span>
          <div style={{ display: "flex", gap: 9 }}>
            <button onClick={onClose} style={{ padding: "9px 16px", borderRadius: 9, fontSize: 12.5, background: "var(--panel-2)", border: "1px solid var(--stroke)", color: "var(--t-mid)" }}>Cancel</button>
            <button onClick={onClose} className="primary-btn">Create Tracker</button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
