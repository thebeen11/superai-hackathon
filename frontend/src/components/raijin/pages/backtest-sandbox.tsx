"use client";
/* ============ RAIJIN — Backtesting Sandbox ============ */
import { useState } from "react";
import type { BacktestResult } from "@/lib/types";
import { useRaijinData } from "@/providers/raijin-provider";
import { runBacktest } from "@/lib/api/raijin";
import { Card, Spark } from "../primitives";
import { PageHead, Field, ResultStat, Legend } from "../shared";

export function BacktestSandbox({ presetTheme }: { presetTheme: string | null }) {
  const d = useRaijinData();
  const [theme, setTheme] = useState(presetTheme ?? d.themes[0].name);
  const [amount, setAmount] = useState(10000);
  const [months, setMonths] = useState(12);
  const [run, setRun] = useState<BacktestResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const themeObj = d.themes.find((t) => t.name === theme) ?? d.themes[0];

  const doRun = async () => {
    setRunning(true);
    setRun(null);
    setError(null);
    try {
      setRun(await runBacktest({ theme, amount, months }));
    } catch {
      setError("Backtest failed — try again.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div>
      <PageHead title="Backtesting Sandbox" sub="thematic portfolio simulation · vs S&P 500" />
      <div className="grid12">
        <Card title="Configure" sub="Freddy · backtest engine" className="span4">
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <Field label="Theme / Basket">
              <select value={theme} onChange={(e) => { setTheme(e.target.value); setRun(null); }} className="r-select">
                {d.backtestThemes.map((t) => (<option key={t} value={t}>{t}</option>))}
              </select>
            </Field>
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: -6 }}>
              {themeObj.stocks.map((s) => (<span key={s} className="mono" style={{ fontSize: 10, padding: "2px 7px", borderRadius: 6, background: "var(--panel-2)", color: "var(--t-mid)" }}>{s}</span>))}
            </div>
            <Field label="Capital deployed">
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className="mono" style={{ fontSize: 16, color: "var(--t-lo)" }}>$</span>
                <input type="range" min="1000" max="100000" step="1000" value={amount} onChange={(e) => { setAmount(+e.target.value); setRun(null); }} className="r-range" />
                <span className="mono" style={{ fontSize: 14, fontWeight: 600, width: 64, textAlign: "right" }}>{amount / 1000}k</span>
              </div>
            </Field>
            <Field label="Lookback window">
              <div style={{ display: "flex", gap: 7 }}>
                {[3, 6, 12].map((m) => (
                  <button key={m} onClick={() => { setMonths(m); setRun(null); }} style={{ flex: 1, padding: "9px 0", borderRadius: 9, fontSize: 12.5, fontWeight: 600, background: months === m ? "color-mix(in oklch, var(--blue) 18%, transparent)" : "var(--panel-2)", border: "1px solid " + (months === m ? "color-mix(in oklch, var(--blue) 50%, transparent)" : "var(--stroke)"), color: months === m ? "var(--blue-bright)" : "var(--t-mid)" }}>{m}M</button>
                ))}
              </div>
            </Field>
            <button onClick={doRun} disabled={running} className="primary-btn" style={{ width: "100%", padding: "12px", fontSize: 13.5, opacity: running ? 0.6 : 1 }}>
              {running ? "Simulating…" : "▶  Run Backtest"}
            </button>
            <div className="mono" style={{ fontSize: 10, color: error ? "var(--down)" : "var(--t-faint)", textAlign: "center", marginTop: -6 }}>{error ?? "pulls historical closes · Polygon.io"}</div>
          </div>
        </Card>

        <Card title="Equity Curve" sub={run ? `$${amount.toLocaleString()} → $${Math.round(run.final).toLocaleString()}` : "run a simulation"} className="span8">
          <div style={{ height: 230, position: "relative" }}>
            {!run && !running && (
              <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: "var(--t-faint)" }}>
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 13 }}>Configure a theme and run a backtest</div>
                  <div className="mono" style={{ fontSize: 11, marginTop: 5 }}>$10k · 12M · vs S&P 500</div>
                </div>
              </div>
            )}
            {running && <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center" }}>
              <span style={{ width: 26, height: 26, borderRadius: 99, border: "2.5px solid var(--blue)", borderTopColor: "transparent", animation: "spin .8s linear infinite" }} /></div>}
            {run && (
              <>
                <div style={{ position: "absolute", inset: 0 }}><Spark key={theme + months + amount} data={run.curve} h={230} fill strokeW={2.8} color="var(--blue-bright)" /></div>
                <div style={{ position: "absolute", inset: 0, opacity: 0.55 }}><Spark key={"spx" + theme + months} data={run.spx} h={230} strokeW={1.8} color="var(--t-lo)" animate={false} /></div>
              </>
            )}
          </div>
          {run && (
            <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
              <ResultStat label="Total return" value={`+${run.ret.toFixed(1)}%`} color="var(--up)" big />
              <ResultStat label="Final value" value={`$${Math.round(run.final).toLocaleString()}`} />
              <ResultStat label="Max drawdown" value={`${run.dd.toFixed(1)}%`} color="var(--down)" />
              <ResultStat label="Alpha vs SPX" value={`+${run.alpha.toFixed(1)}%`} color="var(--blue-bright)" />
            </div>
          )}
          {run && <div style={{ display: "flex", gap: 16, marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--stroke)" }}>
            <Legend c="var(--blue-bright)" label={theme} />
            <Legend c="var(--t-lo)" label="S&P 500" />
          </div>}
        </Card>

        <Card title="What-If Scenario" sub="stress the thesis" className="span12">
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {["Inflation prints 3.5% tomorrow", "Fed holds through Q4", "AI capex guidance cut 10%", "10Y yield spikes to 4.8%"].map((s, i) => (
              <div key={i} style={{ flex: "1 1 220px", display: "flex", alignItems: "center", gap: 11, padding: "12px 14px", borderRadius: 11, background: "var(--inset)", border: "1px solid var(--stroke)" }}>
                <div style={{ width: 30, height: 30, borderRadius: 8, display: "grid", placeItems: "center", background: "color-mix(in oklch, var(--orange) 15%, transparent)", border: "1px solid color-mix(in oklch, var(--orange) 40%, transparent)", color: "var(--orange-bright)", flexShrink: 0 }}>?</div>
                <span style={{ fontSize: 12, color: "var(--t-mid)", flex: 1 }}>{s}</span>
                <span className="mono" style={{ fontSize: 11.5, color: i % 2 ? "var(--down)" : "var(--up)" }}>{i % 2 ? "−" : "+"}{(2 + i * 1.3).toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
