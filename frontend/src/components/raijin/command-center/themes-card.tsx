"use client";
import type { Theme } from "@/lib/types";
import { Card } from "../primitives";

export function ThemesCard({
  themes,
  onRunBacktest,
}: {
  themes: Theme[];
  onRunBacktest: (themeName?: string) => void;
}) {
  const riskC: Record<string, string> = { Low: "var(--up)", Med: "var(--amber)", High: "var(--down)" };
  return (
    <Card title="Thematic Portfolios" sub="Freddy · baskets" className="span7"
      action={<button onClick={() => onRunBacktest(themes[0]?.name)} style={{ fontSize: 11, color: "var(--blue-bright)", background: "none", border: "none" }}>Backtest sandbox →</button>}>
      <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
        {themes.map((t, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 14, padding: "11px 13px", borderRadius: 11, background: "var(--inset)", border: "1px solid var(--stroke)" }}>
            <div style={{ flex: 1.4, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>{t.name}</span>
                <span className="chip" style={{ fontSize: 9, padding: "1px 6px", color: riskC[t.risk], borderColor: "color-mix(in oklch, " + riskC[t.risk] + " 35%, transparent)" }}>{t.risk} · {t.horizon}</span>
              </div>
              <div style={{ fontSize: 11, color: "var(--t-lo)", marginTop: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.strat}</div>
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              {t.stocks.slice(0, 4).map((s) => (<span key={s} className="mono" style={{ fontSize: 9.5, padding: "2px 5px", borderRadius: 5, background: "var(--panel-2)", color: "var(--t-mid)" }}>{s}</span>))}
            </div>
            <div style={{ textAlign: "right", width: 62 }}>
              <div className="mono" style={{ fontSize: 15, fontWeight: 600, color: "var(--up)" }}>+{t.ret}%</div>
              <div className="label-xs" style={{ fontSize: 8 }}>12M sim</div>
            </div>
            <button onClick={() => onRunBacktest(t.name)} style={{ padding: "7px 12px", borderRadius: 8, fontSize: 11.5, fontWeight: 500, background: "color-mix(in oklch, var(--blue) 16%, transparent)", border: "1px solid color-mix(in oklch, var(--blue) 45%, transparent)", color: "var(--blue-bright)" }}>Backtest</button>
          </div>
        ))}
      </div>
    </Card>
  );
}
