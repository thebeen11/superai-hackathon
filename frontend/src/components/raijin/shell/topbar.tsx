"use client";
import { useRaijinData } from "@/providers/raijin-provider";
import { TickerTape } from "../primitives";

export function TopBar() {
  const d = useRaijinData();
  return (
    <header style={{ height: 56, flexShrink: 0, display: "flex", alignItems: "center", gap: 18, padding: "0 20px", borderBottom: "1px solid var(--stroke)", background: "rgba(10,12,18,0.45)", backdropFilter: "blur(12px)", zIndex: 4 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 11, flexShrink: 0 }}>
        <span className="display" style={{ fontSize: 17, fontWeight: 700, letterSpacing: "0.03em" }}>RAIJIN</span>
        <span className="chip" style={{ fontSize: 9, padding: "2px 7px", borderColor: "color-mix(in oklch, var(--up) 40%, transparent)", color: "var(--up)" }}>
          <span style={{ width: 5, height: 5, borderRadius: 99, background: "var(--up)", boxShadow: "0 0 6px var(--up)", animation: "pulse-dot 1.6s infinite" }} />MARKETS OPEN</span>
      </div>
      <div style={{ width: 1, height: 24, background: "var(--stroke)", flexShrink: 0 }} />
      <TickerTape items={d.ticker} />
      <div style={{ width: 1, height: 24, background: "var(--stroke)", flexShrink: 0 }} />
      <div style={{ display: "flex", alignItems: "center", gap: 7, flexShrink: 0 }}>
        <span style={{ width: 6, height: 6, borderRadius: 99, background: "var(--orange)", boxShadow: "0 0 7px var(--orange)", animation: "pulse-dot 1.6s infinite" }} />
        <span className="mono" style={{ fontSize: 11, color: "var(--t-mid)" }}>Wilfred +3 · Andie +2</span>
      </div>
      <div className="chip" style={{ flexShrink: 0, borderColor: "var(--stroke-hi)", padding: "4px 10px" }}>
        <span style={{ color: "var(--t-lo)" }}>ACE</span>
        <span className="mono" style={{ color: "var(--blue-bright)", fontWeight: 600 }}>+{d.ace.value.toFixed(2)}</span>
      </div>
      <span className="mono" style={{ fontSize: 11, color: "var(--t-lo)", flexShrink: 0 }}>{d.now}</span>
    </header>
  );
}
