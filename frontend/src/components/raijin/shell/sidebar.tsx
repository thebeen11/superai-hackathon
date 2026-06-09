"use client";
import type { PageId } from "../shared";

const ICONS: Record<string, string> = {
  command: "M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z",
  signals: "M3 12h3l3-8 4 16 3-10 2 4h3",
  backtest: "M4 20V10M9 20V4M14 20v-7M19 20V8",
  sources: "M12 3c5 0 8 1.3 8 3s-3 3-8 3-8-1.3-8-3 3-3 8-3zM4 6v6c0 1.7 3 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3 3 8 3v-6",
  indicators: "M12 21a9 9 0 1 0-9-9M12 21V12l5-3",
};

const NAV: { id: PageId; label: string; icon: string }[] = [
  { id: "command", label: "Command Center", icon: "command" },
  { id: "signals", label: "Signal Terminal", icon: "signals" },
  { id: "backtest", label: "Backtest Sandbox", icon: "backtest" },
  { id: "sources", label: "Sources & Ledger", icon: "sources" },
  { id: "indicators", label: "Indicators", icon: "indicators" },
];

function NavIcon({ d, active }: { d: string; active: boolean }) {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={active ? 2.1 : 1.7} strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  );
}

export function Sidebar({ page, setPage }: { page: PageId; setPage: (p: PageId) => void }) {
  return (
    <aside style={{ width: 66, flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "center", padding: "16px 0", borderRight: "1px solid var(--stroke)", background: "rgba(255,255,255,0.012)", zIndex: 5 }}>
      <div style={{ width: 38, height: 38, borderRadius: 11, display: "grid", placeItems: "center", marginBottom: 22, background: "linear-gradient(150deg, var(--blue-bright), var(--indigo))", boxShadow: "0 0 18px -4px var(--blue)" }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="#fff"><path d="M13 2L4 14h6l-1 8 9-12h-6z" /></svg>
      </div>
      <nav style={{ display: "flex", flexDirection: "column", gap: 6, flex: 1 }}>
        {NAV.map((n) => {
          const active = page === n.id;
          return (
            <button key={n.id} onClick={() => setPage(n.id)} title={n.label}
              style={{ width: 44, height: 44, borderRadius: 12, display: "grid", placeItems: "center", position: "relative", color: active ? "var(--blue-bright)" : "var(--t-lo)", background: active ? "color-mix(in oklch, var(--blue) 14%, transparent)" : "transparent", border: "1px solid " + (active ? "color-mix(in oklch, var(--blue) 40%, transparent)" : "transparent"), transition: "all .15s" }}
              onMouseEnter={(e) => { if (!active) e.currentTarget.style.color = "var(--t-hi)"; }}
              onMouseLeave={(e) => { if (!active) e.currentTarget.style.color = "var(--t-lo)"; }}>
              <NavIcon d={ICONS[n.icon]} active={active} />
              {active && <span style={{ position: "absolute", left: -9, top: "50%", transform: "translateY(-50%)", width: 3, height: 18, borderRadius: 2, background: "var(--blue-bright)", boxShadow: "0 0 8px var(--blue)" }} />}
            </button>
          );
        })}
      </nav>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 14 }}>
        <button title="Theme" style={{ width: 34, height: 34, borderRadius: 10, display: "grid", placeItems: "center", background: "var(--panel-2)", border: "1px solid var(--stroke)", color: "var(--t-lo)" }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5" strokeLinecap="round" /></svg>
        </button>
        <div style={{ width: 32, height: 32, borderRadius: 99, background: "linear-gradient(150deg, var(--orange-bright), var(--down))", display: "grid", placeItems: "center", fontSize: 12, fontWeight: 700, color: "#fff", boxShadow: "0 0 12px -3px var(--orange)" }}>C</div>
      </div>
    </aside>
  );
}
