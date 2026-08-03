"use client";
/**
 * WtafProvider — loads the dashboard snapshot once and exposes it via context.
 *
 * Components read their data slice with `useWtafData()` (guaranteed non-null,
 * because the shell only mounts children after the snapshot has loaded).
 * `useWtaf()` exposes the raw async state for the loading gate, the `discover()`
 * action, and discovery progress (`discovering` + `discoveryStatus`) so cards and
 * the topbar can show live state. Discovery progress is owned here (not the topbar)
 * so it can be RESUMED after a page reload by reconnecting to the backend job whose
 * id we stash in sessionStorage.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { ActivityEntry, LiveAgentStatus, WtafData } from "@/lib/types";
import { discoverAndProcessStream, getSnapshot, reconnectJobStream } from "@/lib/api/wtaf";
import { isTerminalStreamError, streamSse, type ProgressEvent, type SseInit } from "@/lib/api/sse";
import { toEntry, toLiveStatus } from "@/lib/activity";
import type { DataEngReport } from "@/lib/api/generated/types.gen";

/** Topbar status badge state, driven from streaming progress + the final report. */
export interface DiscoveryStatus {
  tone: "info" | "ok" | "warn" | "err";
  text: string;
}

/** sessionStorage key holding the in-flight job so a reload can reconnect. */
const ACTIVE_JOB_KEY = "wtaf:activeDiscovery";

/** Cap on the rolling in-memory activity feed (newest kept). */
const ACTIVITY_CAP = 200;

interface ActiveJob {
  jobId: string;
  query: string;
  startedAt: number;
}

function readActiveJob(): ActiveJob | null {
  try {
    const raw = sessionStorage.getItem(ACTIVE_JOB_KEY);
    return raw ? (JSON.parse(raw) as ActiveJob) : null;
  } catch {
    return null;
  }
}

function writeActiveJob(job: ActiveJob): void {
  try { sessionStorage.setItem(ACTIVE_JOB_KEY, JSON.stringify(job)); } catch { /* ignore */ }
}

function clearActiveJob(): void {
  try { sessionStorage.removeItem(ACTIVE_JOB_KEY); } catch { /* ignore */ }
}

/** Map one streaming progress event to a short, live badge label. */
function labelFromProgress(evt: ProgressEvent): DiscoveryStatus {
  let text = "Working…";
  if (evt.stage.startsWith("dataeng.item") && typeof evt.data.index === "number") {
    const title = evt.message.replace(/^\[\d+\/\d+\]\s*/, "");
    text = `Cleaning ${evt.data.index}/${evt.data.total}${title ? ` · ${title}` : ""}`;
  } else if (evt.stage === "dataeng") text = "Processing…";
  // Tier 3–5 council stages (auto-chained after data engineering).
  else if (evt.stage === "council.analyst") text = "Analyst desks…";
  else if (evt.stage === "council.debate") text = "Debating…";
  else if (evt.stage === "council.macro") text = "Macro signposts…";
  else if (evt.stage === "council.chairman") text = "Chairman verdict…";
  else if (evt.stage === "council") text = "Convening council…";
  else if (evt.stage.startsWith("discover")) text = "Searching…";
  else if (evt.stage === "refine") text = "Refining…";
  return { tone: "info", text };
}

/** Map the terminal DataEngReport to the final badge. */
function outcomeFromReport(report: DataEngReport): DiscoveryStatus {
  const persisted = report.persisted ?? 0;
  const failed = report.failed ?? 0;
  if (persisted > 0) {
    return { tone: failed > 0 ? "warn" : "ok", text: `Stored ${persisted}${failed > 0 ? ` · ${failed} dropped` : ""}` };
  }
  return { tone: "warn", text: failed > 0 ? `Nothing stored · ${failed} dropped` : "No new sources found" };
}

interface WtafState {
  data: WtafData | null;
  loading: boolean;
  /** A discovery is streaming (per-region loaders, not a full-page reload). */
  discovering: boolean;
  /** Live topbar badge for the current/resumed discovery, or null when idle. */
  discoveryStatus: DiscoveryStatus | null;
  /** Rolling per-agent activity feed (newest last), built from streamed progress. */
  activity: ActivityEntry[];
  /** Live status override per agent id, layered over the static snapshot status. */
  liveStatus: Record<string, LiveAgentStatus>;
  error: Error | null;
  refresh: () => void;
  /** Silently refetch the snapshot (no loading flip) — reconcile after a mutation. */
  revalidate: () => Promise<void>;
  /** Run a live discovery, then refetch the snapshot. */
  discover: (query: string) => Promise<DataEngReport>;
  /**
   * Stream any single background-job endpoint into the shared activity feed, then refetch
   * the snapshot. Used by ingests that run too long to sit inside a request (YouTube
   * channel backfills). Resolves with the job's terminal result.
   */
  runLiveJob: <T>(path: string, init?: SseInit, onJob?: (jobId: string) => void) => Promise<T>;
}

const WtafContext = createContext<WtafState | null>(null);

export function WtafProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<WtafData | null>(null);
  const [loading, setLoading] = useState(true);
  const [discovering, setDiscovering] = useState(false);
  const [discoveryStatus, setDiscoveryStatus] = useState<DiscoveryStatus | null>(null);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [liveStatus, setLiveStatus] = useState<Record<string, LiveAgentStatus>>({});
  const [error, setError] = useState<Error | null>(null);

  // Monotonic counter for stable, unique activity-entry keys across a session.
  const activitySeqRef = useRef(0);

  // Fetch the snapshot. `silent` skips the loading flip and swallows errors —
  // used by post-discovery refetches so the dashboard never blanks (cards stay in
  // their skeleton/updating state via `discovering`). `.then` style (setState in a
  // microtask, not synchronously) keeps the mount effect lint-clean.
  const loadSnapshot = useCallback((opts?: { silent?: boolean }): Promise<void> => {
    const silent = opts?.silent ?? false;
    return getSnapshot()
      .then((d) => { setData(d); setError(null); })
      .catch((e: Error) => {
        if (silent) console.warn("[wtaf] snapshot refetch failed:", e);
        else setError(e);
      })
      .finally(() => { if (!silent) setLoading(false); });
  }, []);

  // Coalesced silent refetch so cards fill progressively as items persist (one in
  // flight at a time; items persist slowly so overlap is rare).
  const refetchingRef = useRef(false);
  const refetchSoon = useCallback(() => {
    if (refetchingRef.current) return;
    refetchingRef.current = true;
    void loadSnapshot({ silent: true }).finally(() => { refetchingRef.current = false; });
  }, [loadSnapshot]);

  // Shared streaming-progress handler: update the badge, and when an item just
  // persisted (`dataeng.item` ok) refetch so its data lands in the cards mid-stream.
  const handleProgress = useCallback((evt: ProgressEvent) => {
    setDiscoveryStatus(labelFromProgress(evt));
    // Append to the per-agent activity feed and update the routed agent's live dot.
    const entry = toEntry(evt, activitySeqRef.current++);
    setActivity((prev) => {
      const next = prev.length >= ACTIVITY_CAP ? prev.slice(prev.length - ACTIVITY_CAP + 1) : prev;
      return [...next, entry];
    });
    const live = toLiveStatus(evt);
    if (live && entry.agentId) setLiveStatus((prev) => ({ ...prev, [entry.agentId!]: live }));
    // Refetch as items persist (Layer 2) and once the council snapshot is ready
    // (Tier 5), so the Tier 3–5 cards fill in the same live pass.
    if (evt.stage === "dataeng.item" && evt.status === "ok") refetchSoon();
    if (evt.stage === "council" && evt.status === "ok") refetchSoon();
  }, [refetchSoon]);

  // Silent refetch for post-mutation reconciliation (watchlist toggle/delete): update
  // the snapshot in place without flipping `loading`, so the page never blanks.
  const revalidate = useCallback(() => loadSnapshot({ silent: true }), [loadSnapshot]);

  // Manual retry from an event handler (e.g. ErrorScreen) — flip loading here.
  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    void loadSnapshot();
  }, [loadSnapshot]);

  // Several runs can stream at once (a discovery plus two channel refreshes), so
  // `discovering` is reference-counted — the first to finish must not clear the others'
  // loading state.
  const liveRunsRef = useRef(0);
  const beginLive = useCallback(() => {
    liveRunsRef.current += 1;
    setDiscovering(true);
  }, []);
  const endLive = useCallback(() => {
    liveRunsRef.current = Math.max(0, liveRunsRef.current - 1);
    if (liveRunsRef.current === 0) setDiscovering(false);
  }, []);

  const runLiveJob = useCallback(
    async <T,>(path: string, init?: SseInit, onJob?: (jobId: string) => void): Promise<T> => {
      beginLive();
      try {
        const result = await streamSse<T>(path, init ?? { method: "POST" }, handleProgress, onJob);
        await loadSnapshot({ silent: true });
        return result;
      } finally {
        endLive();
      }
    },
    [beginLive, endLive, handleProgress, loadSnapshot],
  );

  // Live discovery: stream the ingest (cards show loaders via `discovering`), stash
  // the job id so a reload can reconnect, then silently refetch so new items appear.
  //
  // Not routed through `runLiveJob`: discovery is TWO chained streams (/discover/stream
  // then /dataeng/process/stream) rather than one endpoint, and it owns extra state — the
  // status badge and the reconnect marker. Both paths still funnel into `handleProgress`,
  // which is the single sink that matters.
  const discover = useCallback(
    async (query: string): Promise<DataEngReport> => {
      beginLive();
      setDiscoveryStatus({ tone: "info", text: "Refining…" });
      // A new run = a fresh log; clear prior activity + live statuses.
      setActivity([]);
      setLiveStatus({});
      try {
        const report = await discoverAndProcessStream(
          query,
          handleProgress,
          (jobId) => writeActiveJob({ jobId, query, startedAt: Date.now() }),
        );
        setDiscoveryStatus(outcomeFromReport(report));
        clearActiveJob(); // terminal success — nothing left to reconnect to
        await loadSnapshot({ silent: true });
        return report;
      } catch (e) {
        setDiscoveryStatus({ tone: "err", text: "Discovery failed" });
        // Only drop the marker on a TERMINAL failure. A navigation-abort (page reload)
        // is not terminal — keep the marker so the next page can reconnect & resume.
        if (isTerminalStreamError(e)) clearActiveJob();
        throw e;
      } finally {
        endLive();
      }
    },
    [beginLive, endLive, loadSnapshot, handleProgress],
  );

  // Initial load, plus reconnect to an in-flight discovery after a page reload.
  // All setState happens in async continuations (not synchronously in the effect).
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await loadSnapshot(); // non-silent: clears `loading`, mounts the dashboard
      if (cancelled) return;
      const active = readActiveJob();
      if (!active) return;

      beginLive();
      setDiscoveryStatus({ tone: "info", text: "Reconnecting…" });
      try {
        const report = await reconnectJobStream(active.jobId, (evt) => {
          if (!cancelled) handleProgress(evt);
        });
        if (cancelled) return;
        setDiscoveryStatus(outcomeFromReport(report));
        clearActiveJob(); // terminal success
        await loadSnapshot({ silent: true });
      } catch (e) {
        // Terminal failure (unknown/pruned job → 404, or a server error frame) → drop the
        // marker. A transient abort (another reload) keeps it so we can resume again.
        if (isTerminalStreamError(e)) clearActiveJob();
      } finally {
        endLive();
      }
    })();
    return () => { cancelled = true; };
  }, [beginLive, endLive, loadSnapshot, handleProgress]);

  return (
    <WtafContext.Provider value={{ data, loading, discovering, discoveryStatus, activity, liveStatus, error, refresh, revalidate, discover, runLiveJob }}>
      {children}
    </WtafContext.Provider>
  );
}

/** Raw async state — for the loading/error gate and the discovery action. */
export function useWtaf(): WtafState {
  const ctx = useContext(WtafContext);
  if (!ctx) throw new Error("useWtaf must be used within <WtafProvider>");
  return ctx;
}

/** Loaded snapshot — safe to call from any component rendered past the gate. */
export function useWtafData(): WtafData {
  const { data } = useWtaf();
  if (!data) throw new Error("Wtaf data accessed before it finished loading");
  return data;
}
