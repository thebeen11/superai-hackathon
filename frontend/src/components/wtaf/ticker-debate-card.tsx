"use client";
import { useCallback, useEffect, useState } from "react";
import type { Tier } from "@/lib/types";
import {
  getTickerDebateRun,
  listTickerDebateRuns,
  tickerDebateStreamPath,
  type TickerDebate,
} from "@/lib/api/wtaf";
import type { TickerDebateRunRef } from "@/lib/types";
import { useWtaf } from "@/providers/wtaf-provider";
import { Card, EmptyState } from "./primitives";
import { DebateChamber, hasDebated } from "./command-center/debate-card";
import { DebateModal } from "./modals/debate-modal";
import { EvidenceList } from "./source-link";

/** "02 SEP 11:04" in UTC — runs are stamped by the backend's clock, not the reader's. */
function runLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const month = d.toLocaleString("en", { month: "short", timeZone: "UTC" }).toUpperCase();
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${String(d.getUTCDate()).padStart(2, "0")} ${month} ${hh}:${mm}`;
}

/**
 * The Debate Chamber for one ticker.
 *
 * The Command Center's chamber argues the council's basket — the strongest names across
 * all three desks on a given night — so it says nothing about a ticker that did not make
 * that cut. This card runs the same chamber pointed at one name, over only the corpus
 * that mentions it, and is the reason two ticker pages no longer show the same transcript.
 *
 * It owns its own fetch rather than reading the global snapshot (the precedent set by
 * `command-center/themes-card` and `YoutubeMoments`): debates are run on demand from this
 * page and browsable by date, so a dashboard load should not pay for a list it ignores.
 * The transcript modal is local too — `DebateModal` is a pure `{debate, onClose}`
 * component, so opening this run's transcript needs nothing from the shell, whose
 * `onOpenDebate()` is hardwired to the council-wide debate.
 */
export function TickerDebateCard({ ticker, tiers }: { ticker: string; tiers: Tier[] }) {
  const { runLiveJob } = useWtaf();
  // null = still loading, [] = genuinely never debated.
  const [runs, setRuns] = useState<TickerDebateRunRef[] | null>(null);
  const [runId, setRunId] = useState<number | null>(null);
  const [loaded, setLoaded] = useState<{ id: number; run: TickerDebate | null } | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [transcriptOpen, setTranscriptOpen] = useState(false);

  /** Refetch the picker and select the newest run — what a fresh debate should land on. */
  const loadRuns = useCallback(async () => {
    const rs = await listTickerDebateRuns(ticker);
    setRuns(rs);
    setRunId(rs[0]?.id ?? null);
  }, [ticker]);

  // Mounted under `key={ticker}`, so a ticker change remounts this card rather than
  // resetting five pieces of state by hand — MU's transcript can never flash on NVDA's page.
  useEffect(() => {
    let alive = true;
    listTickerDebateRuns(ticker)
      .then((rs) => {
        if (!alive) return;
        setRuns(rs);
        setRunId(rs[0]?.id ?? null);
      })
      .catch(() => alive && setRuns([]));
    return () => {
      alive = false;
    };
  }, [ticker]);

  useEffect(() => {
    if (runId === null) return;
    let alive = true;
    getTickerDebateRun(ticker, runId)
      .then((run) => alive && setLoaded({ id: runId, run }))
      .catch(() => alive && setLoaded({ id: runId, run: null }));
    return () => {
      alive = false;
    };
  }, [ticker, runId]);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      // Streamed rather than awaited as JSON: six Gemini calls plus Winston's ruling, and
      // `runLiveJob` funnels each round into the activity feed under Freddy on the way.
      await runLiveJob(tickerDebateStreamPath(ticker), { method: "POST" });
      await loadRuns();
    } catch {
      setError("Debate failed — the council may be busy. Try again.");
    } finally {
      setRunning(false);
    }
  }

  const debate = loaded?.run?.debate ?? null;
  const loadingRun = runs === null || (runId !== null && loaded?.id !== runId);
  const hasContent = debate !== null && hasDebated(debate);
  const emptyCorpus = loaded?.run?.sourceCount === 0;

  const picker =
    runs && runs.length > 1 ? (
      <select
        value={runId ?? ""}
        onChange={(e) => setRunId(Number(e.target.value))}
        aria-label={`Past debates on ${ticker}`}
        className="mono"
        style={{
          fontSize: 10.5, padding: "2px 6px", borderRadius: 6, cursor: "pointer",
          background: "var(--panel-2)", color: "var(--t-mid)", border: "1px solid var(--stroke)",
        }}
      >
        {runs.map((r) => (
          <option key={r.id} value={r.id}>
            {runLabel(r.generatedAt)}
          </option>
        ))}
      </select>
    ) : null;

  return (
    <>
      <Card
        title="Debate Chamber"
        sub={hasContent ? `${ticker} · round ${debate.round} / ${debate.rounds}` : ticker}
        className="span8"
        loading={loadingRun && !hasContent}
        updating={(loadingRun || running) && hasContent}
        action={
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {picker}
            {hasContent && (
              <button
                onClick={() => setTranscriptOpen(true)}
                style={{ fontSize: 11, color: "var(--blue-bright)", background: "none", border: "none" }}
              >
                View transcript →
              </button>
            )}
            <button
              onClick={run}
              disabled={running}
              className="primary-btn"
              style={{ padding: "4px 10px", fontSize: 11, opacity: running ? 0.6 : 1 }}
            >
              {running ? "Debating…" : hasContent ? "Re-run" : "Run debate"}
            </button>
          </div>
        }
      >
        {hasContent ? (
          <>
            <DebateChamber
              debate={debate}
              tiers={tiers}
              onOpenTranscript={() => setTranscriptOpen(true)}
            />
            {/* Winston is the only side that cites here, exactly as upstairs — so the
                ruling gets its quote, and an un-anchored one says so rather than hiding. */}
            <EvidenceList
              items={loaded?.run?.verdictEvidence ?? []}
              sources={loaded?.run?.sources}
              emptyLabel="verdict unsourced"
            />
          </>
        ) : (
          <EmptyState
            label={
              error
                ? error
                : emptyCorpus
                  ? `No sources mention ${ticker} yet`
                  : `No debate on ${ticker} yet`
            }
            sub={
              emptyCorpus
                ? "The chamber ran and found nothing to argue over — run a discovery first"
                : "Freddy-Bull vs Freddy-Bear, over the sources that mention this ticker"
            }
            minHeight={180}
          />
        )}
      </Card>
      {transcriptOpen && debate && (
        <DebateModal debate={debate} onClose={() => setTranscriptOpen(false)} />
      )}
    </>
  );
}
