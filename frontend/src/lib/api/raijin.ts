/**
 * Raijin API — typed endpoint functions.
 *
 * Each function is the single connection point for one backend resource.
 * Today they fall back to mock data (USE_MOCK); when the backend is ready,
 * only the `apiFetch(...)` lines below matter and the mock branches drop away.
 */
import type {
  BacktestParams,
  BacktestResult,
  ContextPreview,
  RaijinData,
  Source,
} from "../types";
import { raijinMock } from "../mock-data";
import { apiFetch, mockResolve, USE_MOCK } from "./client";

/** Full dashboard snapshot. Backend: GET /api/snapshot */
export function getSnapshot(): Promise<RaijinData> {
  if (USE_MOCK) return mockResolve(raijinMock);
  return apiFetch<RaijinData>("/api/snapshot");
}

/** Context preview for a tracker. Backend: GET /api/trackers/:name/context */
export function getContextPreview(tracker: string): Promise<ContextPreview> {
  if (USE_MOCK) return mockResolve({ ...raijinMock.contextPreview, tracker });
  return apiFetch<ContextPreview>(
    `/api/trackers/${encodeURIComponent(tracker)}/context`,
  );
}

/** Toggle a data source on/off. Backend: PATCH /api/sources/:name */
export function setSourceLive(name: string, live: boolean): Promise<Source> {
  if (USE_MOCK) {
    const src = raijinMock.sources.find((s) => s.name === name)!;
    return mockResolve({ ...src, live });
  }
  return apiFetch<Source>(`/api/sources/${encodeURIComponent(name)}`, {
    method: "PATCH",
    body: JSON.stringify({ live }),
  });
}

/** Run a thematic backtest. Backend: POST /api/backtest */
export function runBacktest(params: BacktestParams): Promise<BacktestResult> {
  if (USE_MOCK) return mockResolve(mockBacktest(params));
  return apiFetch<BacktestResult>("/api/backtest", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/* ---- mock backtest math (mirrors what the BE engine will return) ---- */
function genCurve(months: number, finalRet: number, vol: number): number[] {
  const n = months * 4; // weekly points
  const out: number[] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const trend = finalRet * Math.pow(t, 0.85);
    const noise = Math.sin(i * 1.3) * vol + Math.cos(i * 0.7) * vol * 0.6;
    out.push(trend + noise * (1 - t * 0.4));
  }
  out[out.length - 1] = finalRet;
  return out;
}

function mockBacktest({ theme, amount, months }: BacktestParams): BacktestResult {
  const themeObj =
    raijinMock.themes.find((t) => t.name === theme) ?? raijinMock.themes[0];
  const base = themeObj.ret * (months / 12);
  const curve = genCurve(months, base, 3.2);
  const spx = genCurve(months, base * 0.42, 1.8);
  const dd = Math.min(...curve.map((v, i) => v - Math.max(...curve.slice(0, i + 1))));
  return {
    curve,
    spx,
    ret: base,
    dd,
    final: amount * (1 + base / 100),
    alpha: base - base * 0.42,
  };
}
