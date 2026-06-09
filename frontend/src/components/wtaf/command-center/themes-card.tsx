"use client";
import type { Theme } from "@/lib/types";
import { Card, EmptyState } from "../primitives";

export function ThemesCard({
  themes,
  onOpenDebate,
}: {
  themes: Theme[];
  onOpenDebate: () => void;
}) {
  const riskC: Record<string, string> = { Low: "var(--up)", Med: "var(--amber)", High: "var(--down)" };
  return (
    <Card title="Thematic Portfolios" sub="Winston · final baskets" className="span12"
      action={<button onClick={onOpenDebate} style={{ fontSize: 11, color: "var(--blue-bright)", background: "none", border: "none" }}>View debate →</button>}>
      {themes.length === 0 ? (
        <EmptyState label="No thematic baskets yet" sub="Run a discovery to group themes · conviction & returns await Winston (Tier 5)" />
      ) : (
      <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
        {themes.map((t, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 14, padding: "11px 13px", borderRadius: 11, background: "var(--inset)", border: "1px solid var(--stroke)" }}>
            <div style={{ flex: 1.4, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>{t.name}</span>
                <span className="chip" style={{ fontSize: 9, padding: "1px 6px", color: riskC[t.risk], borderColor: "color-mix(in oklch, " + riskC[t.risk] + " 35%, transparent)" }}>{t.risk} · hold {t.hold}</span>
              </div>
              <div style={{ fontSize: 11, color: "var(--t-lo)", marginTop: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.strat}</div>
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              {t.stocks.slice(0, 4).map((s) => (<span key={s} className="mono" style={{ fontSize: 9.5, padding: "2px 5px", borderRadius: 5, background: "var(--panel-2)", color: "var(--t-mid)" }}>{s}</span>))}
            </div>
            <div style={{ width: 188, flexShrink: 0, display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 5, height: 5, borderRadius: 99, flexShrink: 0, background: "oklch(0.86 0.05 250)", boxShadow: "0 0 6px oklch(0.86 0.05 250)" }} />
              <span style={{ fontSize: 10.5, color: "var(--t-mid)", lineHeight: 1.3, textWrap: "pretty" }}>{t.verdict}</span>
            </div>
            <div style={{ textAlign: "right", width: 62 }}>
              <div className="mono" style={{ fontSize: 15, fontWeight: 600, color: t.ret > 0 ? "var(--up)" : "var(--t-faint)" }}>{t.ret > 0 ? `+${t.ret}%` : "—"}</div>
              <div className="label-xs" style={{ fontSize: 8 }}>12M sim</div>
            </div>
            <div style={{ width: 64, textAlign: "right" }}>
              <div className="mono" style={{ fontSize: 12, fontWeight: 600, color: t.conviction > 0 ? "var(--t-hi)" : "var(--t-faint)" }}>{t.conviction > 0 ? `${Math.round(t.conviction * 100)}%` : "—"}</div>
              <div className="label-xs" style={{ fontSize: 8 }}>conviction</div>
            </div>
          </div>
        ))}
      </div>
      )}
    </Card>
  );
}
