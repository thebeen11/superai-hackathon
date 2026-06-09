/**
 * Wtaf API — typed endpoint functions.
 *
 * Each function is the single connection point for one backend resource.
 * Today they fall back to mock data (USE_MOCK); when the backend is ready,
 * only the `apiFetch(...)` lines below matter and the mock branches drop away.
 */
import type { ContextPreview, WtafData, Source } from "../types";
import { wtafMock } from "../mock-data";
import { apiFetch, mockResolve, USE_MOCK } from "./client";
import { dataengProcess, discoverPost, listItems } from "./generated/sdk.gen";
import type { DataEngReport } from "./generated/types.gen";
import { itemsToWtafData } from "./adapter";

/**
 * Full dashboard snapshot.
 *
 * Backend reality: only Layers 1–2 exist, so the snapshot is assembled from
 * GET /items via `itemsToWtafData` (source-anchored slices real; Tier 3–5 cards
 * render empty "awaiting" states). `wtafMock` is used ONLY when no API URL is
 * configured (USE_MOCK / offline UI dev) — when the API IS configured, a failure
 * surfaces as an error (ErrorScreen + Retry) rather than silently showing mock.
 */
export async function getSnapshot(): Promise<WtafData> {
  if (USE_MOCK) return mockResolve(wtafMock);
  const { data } = await listItems({ query: { limit: 200 }, throwOnError: true });
  return itemsToWtafData(data ?? []);
}

/**
 * Live discovery: refine + fan out a topic, then run Data Engineering so the
 * results persist and show up on the next snapshot. Uses `auto_proceed` so the
 * one-shot path never stops to ask clarifying questions.
 * Backend: POST /discover → POST /dataeng/process
 */
export async function discoverAndProcess(query: string): Promise<DataEngReport> {
  const { data: discovery } = await discoverPost({
    body: { query, mode: "auto_proceed" },
    throwOnError: true,
  });
  if (!discovery || "questions" in discovery) {
    throw new Error("Discovery returned clarifying questions instead of results");
  }
  const { data: report } = await dataengProcess({
    body: discovery,
    throwOnError: true,
  });
  return report!;
}

/** Context preview for a tracker. Backend: GET /api/trackers/:name/context */
export function getContextPreview(tracker: string): Promise<ContextPreview> {
  if (USE_MOCK) return mockResolve({ ...wtafMock.contextPreview, tracker });
  return apiFetch<ContextPreview>(
    `/api/trackers/${encodeURIComponent(tracker)}/context`,
  );
}

/** Toggle a data source on/off. Backend: PATCH /api/sources/:name */
export function setSourceLive(name: string, live: boolean): Promise<Source> {
  if (USE_MOCK) {
    const src = wtafMock.sources.find((s) => s.name === name)!;
    return mockResolve({ ...src, live });
  }
  return apiFetch<Source>(`/api/sources/${encodeURIComponent(name)}`, {
    method: "PATCH",
    body: JSON.stringify({ live }),
  });
}
