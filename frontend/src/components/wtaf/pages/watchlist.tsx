"use client";
/* ============ WTAF — Watchlist (list + ticker detail routes) ============ */
import Link from "next/link";
import { useWtaf, useWtafData } from "@/providers/wtaf-provider";
import { useShellActions } from "@/providers/shell-ui-provider";
import { Card, MiniBar, EmptyState } from "../primitives";
import { PageHead } from "../shared";
import { DebateCard } from "../command-center/debate-card";
import { fmtChange, fmtPrice, hasQuote } from "@/lib/format";

export function WatchlistPage() {
  const d = useWtafData();
  const { discovering } = useWtaf();
  const isEmpty = d.watchlist.length === 0;

  return (
    <div>
      <PageHead title="Watchlist" sub="bottom-up · click a ticker for detail" />
      <div className="grid12">
        <Card title="Tracked Tickers" sub={`${d.watchlist.length} names`} className="span12"
          loading={discovering && isEmpty} updating={discovering && !isEmpty}
          action={<span className="mono" style={{ fontSize: 11, color: "var(--orange-bright)" }}>{d.watchlist.filter((w) => w.alert).length} alerts</span>}>
          {d.watchlist.length === 0 ? (
            <EmptyState label="No tickers tracked yet" sub="Run a discovery to resolve entities ($TICKER) from sources" minHeight={140} />
          ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {d.watchlist.map((w, i) => (
              <Link key={w.t} href={`/watchlist/${encodeURIComponent(w.t)}`} style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 8px", margin: "0 -8px", background: "transparent", borderBottom: i < d.watchlist.length - 1 ? "1px solid var(--stroke)" : "none", textAlign: "left", borderRadius: 8, transition: "background .15s", cursor: "pointer" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "var(--panel-2)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                <span className="mono" style={{ fontSize: 13, fontWeight: 600, width: 56 }}>{w.t}</span>
                <span style={{ fontSize: 12, color: "var(--t-mid)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{w.n}</span>
                <div style={{ width: 90, flexShrink: 0 }}><MiniBar v={(w.sig + 1) / 2} color={w.sig >= 0 ? "var(--up)" : "var(--down)"} h={4} /></div>
                {w.alert && <span className="chip" style={{ fontSize: 9.5, padding: "2px 6px", borderColor: "color-mix(in oklch, var(--orange) 40%, transparent)", color: "var(--orange-bright)" }}>{w.alert}</span>}
                <span className="mono" style={{ fontSize: 12.5, width: 68, textAlign: "right", color: hasQuote(w) ? undefined : "var(--t-faint)" }}>{fmtPrice(w)}</span>
                <span className="mono" style={{ fontSize: 12, width: 58, textAlign: "right", color: !hasQuote(w) ? "var(--t-faint)" : w.chg >= 0 ? "var(--up)" : "var(--down)" }}>{fmtChange(w)}</span>
                <span style={{ color: "var(--t-faint)", flexShrink: 0 }}>›</span>
              </Link>
            ))}
          </div>
          )}
        </Card>
      </div>
    </div>
  );
}

export function TickerDetailPage({ ticker }: { ticker: string }) {
  const d = useWtafData();
  const { onOpenDebate } = useShellActions();
  const item = d.watchlist.find((w) => w.t.toUpperCase() === ticker.toUpperCase());

  if (!item) {
    return (
      <div>
        <PageHead title={ticker} sub="ticker detail"
          right={<Link href="/watchlist" className="primary-btn" style={{ padding: "8px 14px" }}>‹ Back to Watchlist</Link>} />
        <div className="grid12">
          <Card className="span12">
            <EmptyState label={`No data for ${ticker}`} sub="This ticker is not in the current watchlist" minHeight={140} />
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHead
        title={`${item.t} · ${item.n}`}
        sub="ticker detail · debate & sources"
        right={
          <Link href="/watchlist" style={{ display: "flex", alignItems: "center", gap: 7, padding: "8px 14px", borderRadius: 9, fontSize: 12.5, background: "var(--panel-2)", border: "1px solid var(--stroke)", color: "var(--t-mid)" }}>
            ‹ Back to Watchlist
          </Link>
        }
      />
      <div className="grid12">
        <Card className="span12">
          <div style={{ display: "flex", alignItems: "center", gap: 24, flexWrap: "wrap" }}>
            <Metric label="Price" value={hasQuote(item) ? `$${item.px.toFixed(2)}` : "—"} />
            <Metric label="Change" value={fmtChange(item)} color={!hasQuote(item) ? "var(--t-faint)" : item.chg >= 0 ? "var(--up)" : "var(--down)"} />
            <Metric label="Signal" value={`${item.sig >= 0 ? "+" : ""}${item.sig.toFixed(1)}`} color={item.sig >= 0 ? "var(--up)" : "var(--down)"} />
            {item.alert && (
              <div>
                <div className="label-xs" style={{ fontSize: 8.5, marginBottom: 4 }}>Alert</div>
                <span className="chip" style={{ borderColor: "color-mix(in oklch, var(--orange) 40%, transparent)", color: "var(--orange-bright)" }}>{item.alert}</span>
              </div>
            )}
          </div>
        </Card>

        {/* Debate Chamber — reuses the app's Bull vs Bear structure */}
        <DebateCard debate={d.debate} tiers={d.tiers} onOpenDebate={onOpenDebate} />

        {/* All sources related to this ticker */}
        <Card title="Related Sources" sub={`feeding ${item.t}`} className="span5">
          {d.sources.length === 0 ? (
            <EmptyState label="No sources yet" sub="run a discovery" />
          ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {d.sources.map((s, i) => (
              <div key={s.name} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: i < d.sources.length - 1 ? "1px solid var(--stroke)" : "none" }}>
                <span className="chip" style={{ fontSize: 9, width: 58, justifyContent: "center" }}>{s.kind}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12.5, fontWeight: 500 }}>{s.name}</div>
                  <div className="mono" style={{ fontSize: 10, color: "var(--t-lo)" }}>{s.freq} · {s.items} items</div>
                </div>
                <span style={{ width: 7, height: 7, borderRadius: 99, flexShrink: 0, background: s.live ? "var(--up)" : "var(--t-faint)", boxShadow: s.live ? "0 0 7px var(--up)" : "none" }} />
              </div>
            ))}
          </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div className="label-xs" style={{ fontSize: 8.5, marginBottom: 4 }}>{label}</div>
      <div className="mono display" style={{ fontSize: 20, fontWeight: 700, color: color || "var(--t-hi)" }}>{value}</div>
    </div>
  );
}
