"use client";
/* ============ WTAF — Watchlist (list + ticker detail routes) ============ */
import { useEffect, useState } from "react";
import Link from "next/link";
import { useWtaf, useWtafData } from "@/providers/wtaf-provider";
import { Card, MiniBar, EmptyState } from "../primitives";
import { PageHead, PageButton, ScanToggle, IconButton, RowCheckbox } from "../shared";
import { TickerDebateCard } from "../ticker-debate-card";
import { EvidenceList, SourceLink } from "../source-link";
import { fmtChange, fmtPrice, hasQuote } from "@/lib/format";
import { bulkDeleteWatchlist, deleteWatchlistItem, getYoutubeMatches, setWatchlistActive } from "@/lib/api/wtaf";
import type { WatchItem, YoutubeMatch } from "@/lib/types";

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
  // Bulk selection lives alongside the per-row state; `bulkNotice` is separate from `notice`
  // because a failed bulk call has no single row to hang an error off.
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [confirmingBulk, setConfirmingBulk] = useState(false);
  const [bulkPending, setBulkPending] = useState(false);
  const [bulkNotice, setBulkNotice] = useState<string | null>(null);

  // Fold the optimistic overlay over the snapshot: apply toggled `active`, drop deletes.
  const rows: WatchItem[] = d.watchlist
    .map((w) => ({ ...w, active: overlay[w.t]?.active ?? w.active }))
    .filter((w) => !overlay[w.t]?.deleted);

  const isEmpty = rows.length === 0;
  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  // Clamp during render so a shrinking list (e.g. after delete / re-discovery) never lands on an empty page.
  const safePage = Math.min(page, pageCount - 1);
  const pageItems = rows.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  // A revalidate can drop tickers (a re-discovery, someone else's delete). Keep the selection
  // to what still exists, so a vanished ticker can never be submitted. Returning the same Set
  // when nothing changed keeps this from looping.
  useEffect(() => {
    const live = new Set(d.watchlist.map((w) => w.t));
    setSelected((s) => (
      [...s].every((t) => live.has(t)) ? s : new Set([...s].filter((t) => live.has(t)))
    ));
  }, [d.watchlist]);

  const clearOverlay = (t: string) =>
    setOverlay((o) => { const n = { ...o }; delete n[t]; return n; });

  /** Selection is page-scoped: it resets on paging, so "select all" only ever means what's visible. */
  const goToPage = (next: number) => {
    setPage(next);
    setSelected(new Set());
    setConfirmingBulk(false);
    setBulkNotice(null);
  };

  const pageSelectedCount = pageItems.filter((w) => selected.has(w.t)).length;
  const allPageSelected = pageItems.length > 0 && pageSelectedCount === pageItems.length;

  const toggleOne = (t: string, on: boolean) =>
    setSelected((s) => {
      const n = new Set(s);
      if (on) n.add(t); else n.delete(t);
      return n;
    });

  const toggleAllOnPage = (on: boolean) =>
    setSelected((s) => {
      const n = new Set(s);
      for (const w of pageItems) { if (on) n.add(w.t); else n.delete(w.t); }
      return n;
    });

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

  /** Same optimistic contract as `onDelete`, but one request for the whole selection. */
  async function onBulkDelete() {
    const tickers = [...selected];
    if (tickers.length === 0) return;
    setConfirmingBulk(false);
    setBulkNotice(null);
    const mark = (deleted: boolean) =>
      setOverlay((o) => {
        const n = { ...o };
        for (const t of tickers) n[t] = { ...n[t], deleted };
        return n;
      });
    mark(true);                 // rows vanish now; the safePage clamp handles a shrinking list
    setBulkPending(true);
    try {
      await bulkDeleteWatchlist(tickers);
      await revalidate();       // adapter filters the tombstoned tickers out
      setOverlay((o) => { const n = { ...o }; for (const t of tickers) delete n[t]; return n; });
      setSelected(new Set());
    } catch (e) {
      mark(false);              // revert — and keep the selection so the user can retry
      setBulkNotice(`Remove failed: ${(e as Error)?.message ?? "error"}`);
    } finally {
      setBulkPending(false);
    }
  }

  const alertCount = rows.filter((w) => w.alert).length;

  return (
    <div>
      <PageHead title="Watchlist" sub="bottom-up · toggle scanning or remove tickers" />
      <div className="grid12">
        <Card title="Tracked Tickers" sub={`${rows.length} names`} className="span12"
          loading={discovering && isEmpty} updating={discovering && !isEmpty}
          action={
            /* One fixed-height wrapper for all three states: the 26px IconButtons are taller
               than the bare alerts text, and without it the header — and the whole list —
               jumps down the moment a row is selected. */
            <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 8, height: 26, alignSelf: "center", flexShrink: 0 }}>
              {selected.size === 0 ? (
                <span className="mono" style={{ fontSize: 11, color: "var(--orange-bright)" }}>{alertCount} alerts</span>
              ) : confirmingBulk ? (
                /* Mirrors the per-row confirm, so the bulk path reads the same way. */
                <>
                  <span style={{ fontSize: 11, color: "var(--t-mid)" }}>
                    Remove {selected.size} ticker{selected.size === 1 ? "" : "s"}?
                  </span>
                  <IconButton title="Confirm remove" onClick={onBulkDelete} disabled={bulkPending} danger>✓</IconButton>
                  <IconButton title="Cancel" onClick={() => setConfirmingBulk(false)} disabled={bulkPending}>✕</IconButton>
                </>
              ) : (
                <>
                  <span className="mono" style={{ fontSize: 11, color: "var(--t-mid)" }}>{selected.size} selected</span>
                  <IconButton title="Remove selected" onClick={() => setConfirmingBulk(true)} disabled={bulkPending}>🗑</IconButton>
                  <IconButton title="Clear selection" onClick={() => setSelected(new Set())} disabled={bulkPending}>✕</IconButton>
                </>
              )}
            </div>
          }>
          {isEmpty ? (
            <EmptyState label="No tickers tracked yet" sub="Run a discovery to resolve entities ($TICKER) from sources" minHeight={140} />
          ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {bulkNotice && (
              <div style={{ fontSize: 10.5, color: "var(--down)", paddingBottom: 8 }}>{bulkNotice}</div>
            )}
            {/* Select-all header — scoped to the visible page, aligned with the row boxes. */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "0 8px 8px", margin: "0 -8px", borderBottom: "1px solid var(--stroke)" }}>
              <RowCheckbox
                checked={allPageSelected}
                indeterminate={pageSelectedCount > 0}
                onChange={toggleAllOnPage}
                title={allPageSelected ? "Clear selection on this page" : "Select every ticker on this page"}
                disabled={bulkPending}
              />
              <span className="label-xs" style={{ fontSize: 8.5 }}>
                Select all on this page
              </span>
            </div>
            {pageItems.map((w, i) => {
              const busy = !!pending[w.t] || bulkPending;
              const rowBorder = i < pageItems.length - 1 ? "1px solid var(--stroke)" : "none";
              const picked = selected.has(w.t);
              // Selected rows keep their tint after the pointer leaves, so hover can't clear it.
              const restBg = picked ? "var(--panel-2)" : "transparent";
              return (
                <div key={w.t} style={{ borderBottom: rowBorder }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "9px 8px", margin: "0 -8px", borderRadius: 8, background: restBg, opacity: w.active ? 1 : 0.5, transition: "opacity .15s, background .15s" }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "var(--panel-2)")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = restBg)}>
                    {/* Sibling of the Link, like the actions — inside it, a click would navigate. */}
                    <RowCheckbox
                      checked={picked}
                      onChange={(on) => toggleOne(w.t, on)}
                      title={`Select ${w.t}`}
                      disabled={busy}
                    />
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
                <PageButton label="‹ Prev" disabled={safePage === 0} onClick={() => goToPage(safePage - 1)} />
                <span className="mono" style={{ fontSize: 12, color: "var(--t-mid)" }}>Page {safePage + 1} of {pageCount}</span>
                <PageButton label="Next ›" disabled={safePage >= pageCount - 1} onClick={() => goToPage(safePage + 1)} />
              </div>
            )}
          </div>
          )}
        </Card>
      </div>
    </div>
  );
}

export function TickerDetailPage({ ticker }: { ticker: string }) {
  const d = useWtafData();
  const item = d.watchlist.find((w) => w.t.toUpperCase() === ticker.toUpperCase());
  // Desk calls and documents are keyed on the "$NVDA" form the backend resolves entities to.
  const sym = `$${ticker.replace(/^\$/, "").toUpperCase()}`;
  const takes = d.deskNotes.flatMap((n) =>
    n.stocks.filter((s) => s.ticker.toUpperCase() === sym).map((take) => ({ desk: n.desk, take })),
  );
  const tickerDocs = d.sourceDocs.filter((doc) => doc.tickers.includes(sym));

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

        {/* Debate Chamber, scoped to this ticker — Freddy argues only $SYM, over the
            sources that mention it. The council-wide chamber stays on the Command Center. */}
        <TickerDebateCard key={sym} ticker={sym} tiers={d.tiers} />

        {/* The desk's call on this ticker, with the quotes it was grounded on. */}
        <Card title="Analyst Evidence" sub={`desk calls on ${item.t}`} className="span5">
          {takes.length === 0 ? (
            <EmptyState label="No desk call yet" sub="Awaiting Andie (Tier 3)" />
          ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {takes.map(({ desk, take }, i) => (
              <div key={`${desk}-${i}`} style={{ padding: "10px 0", borderBottom: i < takes.length - 1 ? "1px solid var(--stroke)" : "none" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="chip" style={{ fontSize: 9 }}>Andie-{desk}</span>
                  <span className="mono" style={{ fontSize: 12, fontWeight: 600, color: take.conviction >= 0 ? "var(--up)" : "var(--down)" }}>
                    {take.conviction >= 0 ? "+" : ""}{take.conviction.toFixed(2)}
                  </span>
                  <span className="mono" style={{ fontSize: 10.5, color: "var(--t-lo)" }}>{take.horizon}</span>
                </div>
                {take.rationale && (
                  <div style={{ fontSize: 11.5, color: "var(--t-lo)", marginTop: 4, lineHeight: 1.4, textWrap: "pretty" }}>{take.rationale}</div>
                )}
                <EvidenceList items={take.evidence} sources={d.sourceDocs} />
              </div>
            ))}
          </div>
          )}
        </Card>

        {/* Every document that mentions this ticker — clickable, so the call is checkable. */}
        <Card title="Related Sources" sub={`${tickerDocs.length} mentioning ${item.t}`} className="span7">
          {tickerDocs.length === 0 ? (
            <EmptyState label="No sources mention this ticker" sub="run a discovery" />
          ) : (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {tickerDocs.slice(0, 12).map((doc, i) => (
              <div key={doc.url} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: i < Math.min(tickerDocs.length, 12) - 1 ? "1px solid var(--stroke)" : "none" }}>
                <span className="chip" style={{ fontSize: 9, width: 58, flexShrink: 0, justifyContent: "center" }}>{doc.kind}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <a href={doc.url} target="_blank" rel="noreferrer" style={{ fontSize: 12.5, fontWeight: 500, color: "var(--t-hi)" }} title={doc.url}>
                    {doc.title} ↗
                  </a>
                  <div className="mono" style={{ fontSize: 10, color: "var(--t-lo)", marginTop: 2 }}>{doc.author || doc.host} · {doc.stream}</div>
                </div>
              </div>
            ))}
          </div>
          )}
        </Card>

        <YoutubeMoments ticker={sym} />
      </div>
    </div>
  );
}

/**
 * Moments from followed YouTube channels that discuss this ticker.
 *
 * Fetched here rather than folded into the snapshot: subscriptions are their own resource,
 * and a ticker page should still render if the YouTube source is unconfigured.
 */
function YoutubeMoments({ ticker }: { ticker: string }) {
  const [matches, setMatches] = useState<YoutubeMatch[] | null>(null);

  useEffect(() => {
    let live = true;
    getYoutubeMatches({ ticker, limit: 12 })
      .then((m) => live && setMatches(m))
      .catch(() => live && setMatches([]));
    return () => {
      live = false;
    };
  }, [ticker]);

  // Nothing to say and nothing loading — don't take up a card slot.
  if (matches !== null && matches.length === 0) return null;

  return (
    <Card
      title="From your YouTube channels"
      sub={matches?.length ? `${matches.length} moment${matches.length === 1 ? "" : "s"}` : undefined}
      className="span5"
      loading={matches === null}
    >
      <div style={{ display: "flex", flexDirection: "column" }}>
        {(matches ?? []).map((m, i) => (
          <div
            key={`${m.videoId}-${m.ticker}`}
            style={{
              padding: "10px 0",
              borderBottom: i < (matches?.length ?? 0) - 1 ? "1px solid var(--stroke)" : "none",
            }}
          >
            <SourceLink
              evidence={{ quote: m.quote, sourceUrl: m.videoUrl, timestampStart: m.timestampStart }}
            />
            <div className="mono" style={{ fontSize: 10, color: "var(--t-faint)", marginTop: 3 }}>
              {[m.channelName, m.title].filter(Boolean).join(" · ")}
            </div>
          </div>
        ))}
      </div>
    </Card>
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
