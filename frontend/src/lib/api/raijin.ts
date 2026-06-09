/**
 * Raijin API — typed endpoint functions.
 *
 * Each function is the single connection point for one backend resource.
 * Today they fall back to mock data (USE_MOCK); when the backend is ready,
 * only the `apiFetch(...)` lines below matter and the mock branches drop away.
 */
import type { ContextPreview, RaijinData, Source } from "../types";
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
