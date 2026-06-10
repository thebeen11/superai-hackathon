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
import { councilLatest, dataengProcess, discoverPost, listItems } from "./generated/sdk.gen";
import type { CouncilReport, DataEngReport } from "./generated/types.gen";
import { itemsToWtafData } from "./adapter";
import { streamSse, type ProgressEvent } from "./sse";

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
  const [items, council] = await Promise.all([
    listItems({ query: { limit: 200 }, throwOnError: true }),
    getCouncil(),
  ]);
  return itemsToWtafData(items.data ?? [], council);
}

/**
 * Latest Tier 3–5 council snapshot (debate, baskets, indicators, ACE, briefing).
 * Returns null when no council has run yet (empty DB / fresh start) so the Tier 3–5
 * cards fall back to their "awaiting" empty states. Backend: GET /council/latest
 */
export async function getCouncil(): Promise<CouncilReport | null> {
  if (USE_MOCK) return null;
  try {
    const { data } = await councilLatest({ throwOnError: true });
    return data ?? null;
  } catch {
    return null; // council is best-effort; never block the snapshot on it
  }
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

/**
 * Streaming variant of {@link discoverAndProcess}. `/discover` stays a fast blocking
 * call; the slow per-item Data Engineering runs against `/dataeng/process/stream` so
 * `onProgress` fires for each stage (clean → label → theme → persist). Resolves with
 * the terminal DataEngReport. Backend: POST /discover → POST /dataeng/process/stream
 */
export async function discoverAndProcessStream(
  query: string,
  onProgress: (evt: ProgressEvent) => void,
  onJob?: (jobId: string) => void,
): Promise<DataEngReport> {
  const { data: discovery } = await discoverPost({
    body: { query, mode: "auto_proceed" },
    throwOnError: true,
  });
  if (!discovery || "questions" in discovery) {
    throw new Error("Discovery returned clarifying questions instead of results");
  }
  return streamSse<DataEngReport>(
    "/dataeng/process/stream",
    { method: "POST", body: discovery },
    onProgress,
    onJob,
  );
}

/** A tracked discovery job (backend in-memory registry). */
export interface JobSummary {
  id: string;
  kind: string;
  query: string;
  status: "running" | "done" | "error";
  created_at: number;
}

/** Reconnect to a running/finished job: replays progress, resolves with its DataEngReport. */
export function reconnectJobStream(
  jobId: string,
  onProgress: (evt: ProgressEvent) => void,
): Promise<DataEngReport> {
  return streamSse<DataEngReport>(
    `/dataeng/jobs/${encodeURIComponent(jobId)}/stream`,
    { method: "GET" },
    onProgress,
  );
}

/** List tracked jobs (running by default). Backend: GET /dataeng/jobs */
export function listRunningJobs(): Promise<JobSummary[]> {
  return apiFetch<JobSummary[]>("/dataeng/jobs");
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
