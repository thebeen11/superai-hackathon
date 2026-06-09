"use client";
/**
 * RaijinProvider — loads the dashboard snapshot once and exposes it via context.
 *
 * Components read their data slice with `useRaijinData()` (guaranteed non-null,
 * because the shell only mounts children after the snapshot has loaded).
 * `useRaijin()` exposes the raw async state for the loading gate.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { RaijinData } from "@/lib/types";
import { getSnapshot } from "@/lib/api/raijin";

interface RaijinState {
  data: RaijinData | null;
  loading: boolean;
  error: Error | null;
  refresh: () => void;
}

const RaijinContext = createContext<RaijinState | null>(null);

export function RaijinProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<RaijinData | null>(null);
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
    <RaijinContext.Provider value={{ data, loading, error, refresh }}>
      {children}
    </RaijinContext.Provider>
  );
}

/** Raw async state — for the loading/error gate. */
export function useRaijin(): RaijinState {
  const ctx = useContext(RaijinContext);
  if (!ctx) throw new Error("useRaijin must be used within <RaijinProvider>");
  return ctx;
}

/** Loaded snapshot — safe to call from any component rendered past the gate. */
export function useRaijinData(): RaijinData {
  const { data } = useRaijin();
  if (!data) throw new Error("Raijin data accessed before it finished loading");
  return data;
}
