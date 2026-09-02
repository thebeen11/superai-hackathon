"use client";
import { useEffect, useState } from "react";
import { getThematicRun, listThematicRuns } from "@/lib/api/wtaf";
import { TIMEFRAME_LABEL, TIMEFRAMES } from "@/lib/types";
import type { Theme, ThematicRunRef, Timeframe } from "@/lib/types";
import { useWtafData } from "@/providers/wtaf-provider";
import { Card, EmptyState } from "../primitives";
import { EvidenceList } from "../source-link";

type Filter = Timeframe | "All";

/** "31 AUG" in UTC — runs are stamped by the backend's clock, not the reader's. */
function runLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const month = d.toLocaleString("en", { month: "short", timeZone: "UTC" }).toUpperCase();
  return `${String(d.getUTCDate()).padStart(2, "0")} ${month}`;
}

/**
 * Thematic Analysis — Winston's weekly baskets.
 *
 * This card owns its own fetch rather than reading the global snapshot: thematic runs are
 * weekly and browsable by date, so a dashboard load should not pay for a run list it
 * usually ignores (the same reasoning as the YouTube sources tab). The run picker is what
 * makes past weeks reachable at all — every run is stored, not just the newest.
 */
export function ThemesCard({ onOpenDebate }: { onOpenDebate: () => void }) {
  const d = useWtafData();
  // `runs === null` means the list is still in flight; [] means there are genuinely none.
  const [runs, setRuns] = useState<ThematicRunRef[] | null>(null);
  const [runId, setRunId] = useState<number | null>(null);
  // Keyed by the run it belongs to, so `loading` is derived rather than a second state
  // machine — and switching runs keeps the previous week's rows on screen meanwhile.
  const [loaded, setLoaded] = useState<{ id: number; themes: Theme[] } | null>(null);
  const [filter, setFilter] = useState<Filter>("All");

  useEffect(() => {
    let alive = true;
    listThematicRuns()
      .then((rs) => {
        if (!alive) return;
        setRuns(rs);
        setRunId(rs[0]?.id ?? null);
      })
      .catch(() => alive && setRuns([]));
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (runId === null) return;
    let alive = true;
    getThematicRun(runId)
      .then((run) => alive && setLoaded({ id: runId, themes: run?.themes ?? [] }))
      .catch(() => alive && setLoaded({ id: runId, themes: [] }));
    return () => {
      alive = false;
    };
  }, [runId]);

  const themes = loaded?.themes ?? [];
  const loading = runs === null || (runId !== null && loaded?.id !== runId);

  const riskC: Record<string, string> = { Low: "var(--up)", Med: "var(--amber)", High: "var(--down)" };
  // Conviction is a "higher is better" metric: high = green, mid = amber, low = red.
  const convictionColor = (c: number) =>
    c <= 0 ? "var(--t-faint)" : c >= 0.6 ? "var(--up)" : c >= 0.45 ? "var(--amber)" : "var(--down)";

  const shown = filter === "All" ? themes : themes.filter((t) => t.timeframe === filter);
  const count = (f: Filter) =>
    f === "All" ? themes.length : themes.filter((t) => t.timeframe === f).length;
  const isEmpty = themes.length === 0;

  const picker =
    runs && runs.length > 0 ? (
      <select
        value={runId ?? ""}
        onChange={(e) => setRunId(Number(e.target.value))}
        aria-label="Thematic Analysis run"
        className="mono"
        style={{
          fontSize: 10.5, padding: "2px 6px", borderRadius: 6, cursor: "pointer",
          background: "var(--panel-2)", color: "var(--t-mid)", border: "1px solid var(--stroke)",
        }}
      >
        {runs.map((r) => (
          <option key={r.id} value={r.id}>
            {runLabel(r.generatedAt)} · {r.basketCount} theme{r.basketCount === 1 ? "" : "s"}
          </option>
        ))}
      </select>
    ) : null;

  return (
    <Card
      title="Thematic Analysis"
      sub="Winston · weekly"
      className="span9"
      loading={loading && isEmpty}
      updating={loading && !isEmpty}
      action={
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {picker}
          <button onClick={onOpenDebate} style={{ fontSize: 11, color: "var(--blue-bright)", background: "none", border: "none" }}>View debate →</button>
        </div>
      }
    >
      {isEmpty ? (
        <EmptyState
          label="No thematic run yet"
          sub="Thematic Analysis runs weekly · trigger one from the Agent Console"
        />
      ) : (
        <>
          {/* Timeframe filter — local state, same underline treatment as the page sub-tabs.
              Counts stay visible so an empty bucket reads as "none this week", not a bug. */}
          <div style={{ display: "flex", gap: 4, marginBottom: 12, borderBottom: "1px solid var(--stroke)" }}>
            {(["All", ...TIMEFRAMES] as Filter[]).map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                style={{
                  padding: "6px 10px",
                  fontSize: 11,
                  fontWeight: filter === f ? 600 : 400,
                  background: "transparent",
                  border: "none",
                  borderBottom: "2px solid " + (filter === f ? "var(--blue-bright)" : "transparent"),
                  color: filter === f ? "var(--t-hi)" : "var(--t-lo)",
                  cursor: "pointer",
                  marginBottom: -1,
                }}
              >
                {f === "All" ? "All" : `${f} (${TIMEFRAME_LABEL[f]})`}
                <span className="mono" style={{ fontSize: 9.5, color: "var(--t-faint)", marginLeft: 5 }}>{count(f)}</span>
              </button>
            ))}
          </div>
          {shown.length === 0 ? (
            <EmptyState label={`No ${filter} themes in this run`} minHeight={64} />
          ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
            {shown.map((t, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 14, padding: "11px 13px", borderRadius: 11, background: "var(--inset)", border: "1px solid var(--stroke)" }}>
                <div style={{ flex: 1.4, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{t.name}</span>
                    <span className="chip" style={{ fontSize: 9, padding: "1px 6px", color: riskC[t.risk], borderColor: "color-mix(in oklch, " + riskC[t.risk] + " 35%, transparent)" }}>{t.risk} · hold {t.hold}</span>
                    <span className="chip" style={{ fontSize: 9, padding: "1px 6px", color: "var(--t-mid)" }}>{t.timeframe} · {TIMEFRAME_LABEL[t.timeframe]}</span>
                  </div>
                  <div style={{ fontSize: 11, color: "var(--t-lo)", marginTop: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.strat}</div>
                  <EvidenceList items={t.evidence} sources={d.sourceDocs} />
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
                  <div className="mono" style={{ fontSize: 12, fontWeight: 600, color: convictionColor(t.conviction) }}>{t.conviction > 0 ? `${Math.round(t.conviction * 100)}%` : "—"}</div>
                  <div className="label-xs" style={{ fontSize: 8 }}>conviction</div>
                </div>
              </div>
            ))}
          </div>
          )}
        </>
      )}
    </Card>
  );
}
