"use client";
/* ============ WTAF — Watchlist (list + ticker detail routes) ============ */
import { useState, type ReactNode } from "react";
import Link from "next/link";
import { useWtaf, useWtafData } from "@/providers/wtaf-provider";
import { useShellActions } from "@/providers/shell-ui-provider";
import { Card, MiniBar, EmptyState } from "../primitives";
import { PageHead, PageButton } from "../shared";
import { DebateCard } from "../command-center/debate-card";
import { fmtChange, fmtPrice, hasQuote } from "@/lib/format";
import { deleteWatchlistItem, setWatchlistActive } from "@/lib/api/wtaf";
import type { WatchItem } from "@/lib/types";

const PAGE_SIZE = 25;

/** Optimistic per-ticker overlay applied over the derived snapshot until revalidation. */
type Overlay = Record<string, { active?: boolean; deleted?: boolean }>;

export function WatchlistPage() {
  const d = useWtafData();
  const { discovering, revalidate } = useWtaf();

  const [page, setPage] = useState(0);
  const [overlay, setOverlay] = useState<Overlay>({});
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const [confirming, setConfirming] = useState<string | null>(null);
  const [notice, setNotice] = useState<Record<string, string>>({});

  // Fold the optimistic overlay over the snapshot: apply toggled `active`, drop deletes.
  const rows: WatchItem[] = d.watchlist
    .map((w) => ({ ...w, active: overlay[w.t]?.active ?? w.active }))
    .filter((w) => !overlay[w.t]?.deleted);

  const isEmpty = rows.length === 0;
  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  // Clamp during render so a shrinking list (e.g. after delete / re-discovery) never lands on an empty page.
  const safePage = Math.min(page, pageCount - 1);
  const pageItems = rows.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  const clearOverlay = (t: string) =>
    setOverlay((o) => { const n = { ...o }; delete n[t]; return n; });

  async function onToggle(w: WatchItem) {
    const next = !w.active;
    setNotice((n) => { const m = { ...n }; delete m[w.t]; return m; });
    setOverlay((o) => ({ ...o, [w.t]: { ...o[w.t], active: next } }));
    setPending((p) => ({ ...p, [w.t]: true }));
    try {
      await setWatchlistActive(w.t, next);
      await revalidate();       // snapshot now carries the server state…
      clearOverlay(w.t);        // …so the optimistic overlay can drop away
    } catch (e) {
      setOverlay((o) => ({ ...o, [w.t]: { ...o[w.t], active: w.active } })); // revert
      setNotice((n) => ({ ...n, [w.t]: `Toggle failed: ${(e as Error)?.message ?? "error"}` }));
    } finally {
      setPending((p) => ({ ...p, [w.t]: false }));
    }
  }

  async function onDelete(w: WatchItem) {
    setConfirming(null);
    setNotice((n) => { const m = { ...n }; delete m[w.t]; return m; });
    setOverlay((o) => ({ ...o, [w.t]: { ...o[w.t], deleted: true } }));
    setPending((p) => ({ ...p, [w.t]: true }));
    try {
      await deleteWatchlistItem(w.t);
      await revalidate();       // adapter now filters the tombstoned ticker out
      clearOverlay(w.t);
    } catch (e) {
      setOverlay((o) => ({ ...o, [w.t]: { ...o[w.t], deleted: false } })); // revert
      setNotice((n) => ({ ...n, [w.t]: `Delete failed: ${(e as Error)?.message ?? "error"}` }));
    } finally {
      setPending((p) => ({ ...p, [w.t]: false }));
    }
  }

  const alertCount = rows.filter((w) => w.alert).length;

  return (
    <div>
      <PageHead title="Watchlist" sub="bottom-up · toggle scanning or remove a ticker" />
      <div className="grid12">
        <Card title="Tracked Tickers" sub={`${rows.length} names`} className="span12"
          loading={discovering && isEmpty} updating={discovering && !isEmpty}
          action={<span className="mono" style={{ fontSize: 11, color: "var(--orange-bright)" }}>{alertCount} alerts</span>}>
          {isEmpty ? (
            <EmptyState label="No tickers tracked yet" sub="Run a discovery to resolve entities ($TICKER) from sources" minHeight={140} />
          ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {pageItems.map((w, i) => {
              const busy = !!pending[w.t];
              const rowBorder = i < pageItems.length - 1 ? "1px solid var(--stroke)" : "none";
              return (
                <div key={w.t} style={{ borderBottom: rowBorder }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "9px 8px", margin: "0 -8px", borderRadius: 8, opacity: w.active ? 1 : 0.5, transition: "opacity .15s, background .15s" }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "var(--panel-2)")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                    {/* Clickable info area — navigates to the ticker detail. */}
                    <Link href={`/watchlist/${encodeURIComponent(w.t)}`} style={{ display: "flex", alignItems: "center", gap: 12, flex: 1, minWidth: 0, textAlign: "left", cursor: "pointer" }}>
                      <span className="mono" style={{ fontSize: 13, fontWeight: 600, width: 56 }}>{w.t}</span>
                      <span style={{ fontSize: 12, color: "var(--t-mid)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{w.n}</span>
                      <div style={{ width: 90, flexShrink: 0 }}><MiniBar v={(w.sig + 1) / 2} color={w.sig >= 0 ? "var(--up)" : "var(--down)"} h={4} /></div>
                      {w.alert && <span className="chip" style={{ fontSize: 9.5, padding: "2px 6px", borderColor: "color-mix(in oklch, var(--orange) 40%, transparent)", color: "var(--orange-bright)" }}>{w.alert}</span>}
                      <span className="mono" style={{ fontSize: 12.5, width: 68, textAlign: "right", color: hasQuote(w) ? undefined : "var(--t-faint)" }}>{fmtPrice(w)}</span>
                      <span className="mono" style={{ fontSize: 12, width: 58, textAlign: "right", color: !hasQuote(w) ? "var(--t-faint)" : w.chg >= 0 ? "var(--up)" : "var(--down)" }}>{fmtChange(w)}</span>
                    </Link>
                    {/* Actions — siblings of the Link so they never navigate. */}
                    {confirming === w.t ? (
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
                        <span style={{ fontSize: 11, color: "var(--t-mid)" }}>Remove?</span>
                        <IconButton title="Confirm remove" onClick={() => onDelete(w)} disabled={busy} danger>✓</IconButton>
                        <IconButton title="Cancel" onClick={() => setConfirming(null)} disabled={busy}>✕</IconButton>
                      </div>
                    ) : (
                      <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
                        <ScanToggle on={w.active} pending={busy} onToggle={() => onToggle(w)} />
                        <IconButton title="Remove from watchlist" onClick={() => setConfirming(w.t)} disabled={busy}>🗑</IconButton>
                      </div>
                    )}
                  </div>
                  {notice[w.t] && (
                    <div style={{ fontSize: 10.5, color: "var(--down)", padding: "0 8px 8px", margin: "0 -8px" }}>{notice[w.t]}</div>
                  )}
                </div>
              );
            })}
            {pageCount > 1 && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--stroke)" }}>
                <PageButton label="‹ Prev" disabled={safePage === 0} onClick={() => setPage(safePage - 1)} />
                <span className="mono" style={{ fontSize: 12, color: "var(--t-mid)" }}>Page {safePage + 1} of {pageCount}</span>
                <PageButton label="Next ›" disabled={safePage >= pageCount - 1} onClick={() => setPage(safePage + 1)} />
              </div>
            )}
          </div>
          )}
        </Card>
      </div>
    </div>
  );
}

/** On/off pill for per-ticker scanning (pattern mirrors the Agent Console mental-model switch). */
function ScanToggle({ on, pending, onToggle }: { on: boolean; pending: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={pending}
      aria-pressed={on}
      title={on ? "Scanning on — click to pause" : "Scanning paused — click to resume"}
      style={{
        width: 34, height: 19, borderRadius: 99, flexShrink: 0, position: "relative",
        border: "1px solid " + (on ? "color-mix(in oklch, var(--orange-bright) 55%, transparent)" : "var(--stroke-hi)"),
        background: on ? "color-mix(in oklch, var(--orange-bright) 26%, transparent)" : "var(--panel-2)",
        cursor: pending ? "default" : "pointer", opacity: pending ? 0.5 : 1, transition: "background .15s",
      }}
    >
      <span style={{ position: "absolute", top: 2, left: on ? 16 : 2, width: 13, height: 13, borderRadius: 99, background: on ? "var(--orange-bright)" : "var(--t-faint)", boxShadow: on ? "0 0 8px var(--orange-bright)" : "none", transition: "left .15s" }} />
    </button>
  );
}

/** Small square glyph button for the delete / confirm actions. */
function IconButton({ children, title, onClick, disabled, danger }: { children: ReactNode; title: string; onClick: () => void; disabled?: boolean; danger?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{
        width: 26, height: 26, display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 13, lineHeight: 1, borderRadius: 7, flexShrink: 0,
        background: "var(--panel-2)", border: "1px solid " + (danger ? "color-mix(in oklch, var(--down) 45%, transparent)" : "var(--stroke)"),
        color: danger ? "var(--down)" : "var(--t-mid)",
        cursor: disabled ? "default" : "pointer", opacity: disabled ? 0.4 : 1, transition: "opacity .15s",
      }}
    >
      {children}
    </button>
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
