"use client";
/**
 * WtafProvider — loads the dashboard snapshot once and exposes it via context.
 *
 * Components read their data slice with `useWtafData()` (guaranteed non-null,
 * because the shell only mounts children after the snapshot has loaded).
 * `useWtaf()` exposes the raw async state for the loading gate.
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
import { getSnapshot } from "@/lib/api/wtaf";

interface WtafState {
  data: WtafData | null;
  loading: boolean;
  error: Error | null;
  refresh: () => void;
}

const WtafContext = createContext<WtafState | null>(null);

export function WtafProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<WtafData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  // Async-only state updates (safe to call from an effect — no sync setState).
  const fetchData = useCallback(() => {
    getSnapshot()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e: Error) => setError(e))
      .finally(() => setLoading(false));
  }, []);

  // Manual retry from an event handler — fine to flip loading synchronously here.
  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <WtafContext.Provider value={{ data, loading, error, refresh }}>
      {children}
    </WtafContext.Provider>
  );
}

/** Raw async state — for the loading/error gate. */
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
