"use client";
/**
 * WtafProvider — loads the dashboard snapshot once and exposes it via context.
 *
 * Components read their data slice with `useWtafData()` (guaranteed non-null,
 * because the shell only mounts children after the snapshot has loaded).
 * `useWtaf()` exposes the raw async state for the loading gate, plus the
 * `discover()` action and a `discovering` flag so cards can show per-region
 * loading states while a discovery streams (instead of a full-page reload).
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { WtafData } from "@/lib/types";
import { discoverAndProcessStream, getSnapshot } from "@/lib/api/wtaf";
import type { ProgressEvent } from "@/lib/api/sse";
import type { DataEngReport } from "@/lib/api/generated/types.gen";

interface WtafState {
  data: WtafData | null;
  loading: boolean;
  /** A discovery is streaming (per-region loaders, not a full-page reload). */
  discovering: boolean;
  error: Error | null;
  refresh: () => void;
  /** Run a live discovery, then refetch the snapshot. Reports progress via `onProgress`. */
  discover: (query: string, onProgress?: (evt: ProgressEvent) => void) => Promise<DataEngReport>;
}

const WtafContext = createContext<WtafState | null>(null);

export function WtafProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<WtafData | null>(null);
  const [loading, setLoading] = useState(true);
  const [discovering, setDiscovering] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // Fetch the snapshot. `silent` skips the loading flip and swallows errors —
  // used by the post-discovery refetch so the dashboard never blanks (cards stay
  // in their skeleton/updating state via `discovering` instead). `.then` style
  // (setState in a microtask, not synchronously) keeps the effect lint-clean.
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

  // Manual retry from an event handler (e.g. ErrorScreen) — flip loading here.
  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    void loadSnapshot();
  }, [loadSnapshot]);

  // Live discovery: stream the ingest (cards show loaders via `discovering`),
  // then silently refetch so the new items populate without a full-page reload.
  const discover = useCallback(
    async (query: string, onProgress?: (evt: ProgressEvent) => void): Promise<DataEngReport> => {
      setDiscovering(true);
      try {
        const report = await discoverAndProcessStream(query, onProgress ?? (() => {}));
        await loadSnapshot({ silent: true });
        return report;
      } finally {
        setDiscovering(false);
      }
    },
    [loadSnapshot],
  );

  useEffect(() => {
    void loadSnapshot();
  }, [loadSnapshot]);

  return (
    <WtafContext.Provider value={{ data, loading, discovering, error, refresh, discover }}>
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
