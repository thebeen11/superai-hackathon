"use client";
import Image from "next/image";
import { useState, type FormEvent } from "react";
import type { TickerItem } from "@/lib/types";
import { useWtaf, useWtafData } from "@/providers/wtaf-provider";
import { USE_MOCK } from "@/lib/api/client";
import { discoverAndProcess } from "@/lib/api/wtaf";

export function TopBar() {
  const d = useWtafData();
  const { refresh } = useWtaf();
  const [tickers, setTickers] = useState<TickerItem[]>(d.ticker);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);

  const addTicker = (e: FormEvent) => {
    e.preventDefault();
    const topic = query.trim();
    if (!topic || busy) return;

    // Optimistic ticker chip (immediate feedback) when the input looks like a symbol.
    const sym = topic.replace(/^\$/, "").toUpperCase();
    const symbol = `$${sym}`;
    if (/^[A-Z.]{1,6}$/.test(sym) && !tickers.some((t) => t.t.toUpperCase() === symbol)) {
      setTickers((prev) => [{ t: symbol, px: "—", chg: 0 }, ...prev]);
    }
    setQuery("");

    // Live mode: treat the input as a discovery topic — ingest it, then refresh
    // so the adapter repopulates Sources / Trackers / Watchlist from real items.
    if (!USE_MOCK) {
      setBusy(true);
      discoverAndProcess(topic)
        .then(() => refresh())
        .catch((err) => console.warn("[wtaf] discovery failed:", err))
        .finally(() => setBusy(false));
    }
  };

  return (
    <header style={{ height: 56, flexShrink: 0, display: "flex", alignItems: "center", gap: 16, padding: "0 20px", borderBottom: "1px solid var(--stroke)", background: "rgba(10,12,18,0.45)", backdropFilter: "blur(12px)", zIndex: 4 }}>
      {/* App name */}
      <div style={{ display: "flex", alignItems: "center", gap: 9, flexShrink: 0 }}>
        <Image src="/logo.jpg" alt="WTAF Fund" width={26} height={26} priority style={{ borderRadius: 7, objectFit: "cover" }} />
        <span className="display" style={{ fontSize: 17, fontWeight: 700, letterSpacing: "0.03em" }}>WTAF Fund</span>
      </div>

      <div style={{ width: 1, height: 24, background: "var(--stroke)", flexShrink: 0 }} />

      {/* Add-ticker field */}
      <form onSubmit={addTicker} style={{ display: "flex", alignItems: "center", gap: 7, flexShrink: 0 }}>
        <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--t-faint)" strokeWidth="2" style={{ position: "absolute", left: 9, pointerEvents: "none" }}>
            <circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" strokeLinecap="round" />
          </svg>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={busy}
            placeholder={busy ? "Discovering…" : USE_MOCK ? "Add ticker…" : "Discover topic…"}
            aria-label={USE_MOCK ? "Add stock ticker" : "Discover a research topic"}
            className="mono"
            style={{ width: 170, padding: "7px 10px 7px 28px", borderRadius: 8, fontSize: 12, background: "var(--inset)", border: "1px solid var(--stroke)", color: "var(--t-hi)", outline: "none", opacity: busy ? 0.6 : 1 }}
            onFocus={(e) => (e.currentTarget.style.borderColor = "color-mix(in oklch, var(--blue) 50%, transparent)")}
            onBlur={(e) => (e.currentTarget.style.borderColor = "var(--stroke)")}
          />
        </div>
        <button type="submit" disabled={busy} title={USE_MOCK ? "Add ticker" : "Discover topic"} style={{ width: 30, height: 30, borderRadius: 8, display: "grid", placeItems: "center", flexShrink: 0, background: "color-mix(in oklch, var(--blue) 16%, transparent)", border: "1px solid color-mix(in oklch, var(--blue) 45%, transparent)", color: "var(--blue-bright)", fontSize: 16, lineHeight: 1, cursor: busy ? "default" : "pointer", opacity: busy ? 0.6 : 1 }}>{busy ? "…" : "+"}</button>
      </form>

      {/* push datetime to the right */}
      <div style={{ flex: 1 }} />

      {/* Datetime */}
      <span className="mono" style={{ fontSize: 11, color: "var(--t-lo)", flexShrink: 0 }}>{d.now}</span>
    </header>
  );
}
