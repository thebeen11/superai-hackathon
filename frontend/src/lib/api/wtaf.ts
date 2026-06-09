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

/** Full dashboard snapshot. Backend: GET /api/snapshot */
export function getSnapshot(): Promise<WtafData> {
  if (USE_MOCK) return mockResolve(wtafMock);
  return apiFetch<WtafData>("/api/snapshot");
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
