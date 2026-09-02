/**
 * Wtaf API — typed endpoint functions.
 *
 * Each function is the single connection point for one backend resource.
 * Today they fall back to mock data (USE_MOCK); when the backend is ready,
 * only the `apiFetch(...)` lines below matter and the mock branches drop away.
 */
import type {
  ContextPreview,
  Theme,
  ThematicRunRef,
  WtafData,
  Source,
  WatchlistEntry,
  YoutubeChannel,
  YoutubeIngestReport,
  YoutubeJobRef,
  YoutubeMatch,
} from "../types";
import {
  thematicRunMock,
  thematicRunRefsMock,
  wtafMock,
  youtubeChannelsMock,
  youtubeMatchesMock,
} from "../mock-data";
import { apiFetch, mockResolve, USE_MOCK } from "./client";
import {
  agentEffectivePrompt,
  councilLatest,
  dataengProcess,
  getThematicRunEndpoint,
  latestThematicRun,
  listThematicRunsEndpoint,
  discoverPost,
  listAgents,
  listItems,
  listPrompts,
  resetAgentMentalModels,
  resetPrompt,
  setAgentMentalModels,
  updatePrompt,
} from "./generated/sdk.gen";
import type {
  AgentView,
  Clarify,
  CouncilReport,
  DataEngReport,
  DiscoveryResultOutput,
  EffectivePrompt,
  PromptView,
} from "./generated/types.gen";
import { itemsToWtafData, thematicRunRefs, thematicRunToThemes } from "./adapter";
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
  const [items, council, watchlist] = await Promise.all([
    listItems({ query: { limit: 200 }, throwOnError: true }),
    getCouncil(),
    getWatchlistOverrides(),
  ]);
  return itemsToWtafData(items.data ?? [], council, watchlist);
}

/**
 * Latest Tier 3–5 council snapshot (debate, indicators, ACE, briefing).
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
 * Dated Thematic Analysis runs for the run picker, newest first.
 *
 * Not part of `getSnapshot`: thematic runs are weekly and browsable by date, so the card
 * owns this fetch rather than every dashboard load paying for a list it usually ignores.
 * Backend: GET /api/thematic/runs
 */
export async function listThematicRuns(): Promise<ThematicRunRef[]> {
  if (USE_MOCK) return mockResolve(thematicRunRefsMock);
  const { data } = await listThematicRunsEndpoint({ throwOnError: true });
  return thematicRunRefs(data ?? []);
}

/**
 * The themes of one run — a specific id, or "latest" for the most recent.
 *
 * Returns null when no run exists yet, so the card shows its honest empty state rather
 * than last week's themes or invented ones.
 * Backend: GET /api/thematic/runs/{id} | /api/thematic/runs/latest
 */
export async function getThematicRun(
  id: number | "latest" = "latest",
): Promise<{ id: number | null; generatedAt: string; themes: Theme[] } | null> {
  if (USE_MOCK) return mockResolve(thematicRunMock(id));
  const { data } =
    id === "latest"
      ? await latestThematicRun({ throwOnError: true })
      : await getThematicRunEndpoint({ path: { run_id: id }, throwOnError: true });
  if (!data) return null;
  return {
    id: data.id ?? null,
    generatedAt: data.generated_at ?? "",
    themes: thematicRunToThemes(data),
  };
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
 * Streaming variant of {@link discoverAndProcess}. BOTH phases stream into the same
 * `onProgress`: `/discover/stream` surfaces the Tier-1 refine + per-source events
 * (`discover.web`, `discover.youtube`) so the activity log shows Wilfred-News /
 * Wilfred-Video lines, then the slow per-item Data Engineering runs against
 * `/dataeng/process/stream` (clean → label → theme → persist → council). Resolves with
 * the terminal DataEngReport. Backend: POST /discover/stream → POST /dataeng/process/stream
 */
export async function discoverAndProcessStream(
  query: string,
  onProgress: (evt: ProgressEvent) => void,
  onJob?: (jobId: string) => void,
): Promise<DataEngReport> {
  // Stream the discovery phase so refine + per-source progress reaches the activity feed.
  // (No job here — discovery is fast; reload-reconnect is owned by the dataeng stream.)
  const discovery = await streamSse<DiscoveryResultOutput | Clarify>(
    "/discover/stream",
    { method: "POST", body: { query, mode: "auto_proceed" } },
    onProgress,
  );
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

/* ============ Agent Console — agents + their editable prompt layers ============ */

export type { AgentView, EffectivePrompt, PromptView };

/** The agent roster in council order, with tools + enabled frameworks. Backend: GET /api/agents */
export async function getAgents(): Promise<AgentView[]> {
  if (USE_MOCK) return [];
  const { data } = await listAgents({ throwOnError: true });
  return data ?? [];
}

/** Choose which reasoning frameworks an agent runs. Backend: PUT /api/agents/:id/mental-models */
export async function saveMentalModels(
  agentId: string,
  keys: string[],
): Promise<AgentView> {
  const { data } = await setAgentMentalModels({
    path: { agent_id: agentId },
    body: { keys },
    throwOnError: true,
  });
  return data!;
}

/** Restore an agent's built-in frameworks. Backend: DELETE /api/agents/:id/mental-models */
export async function resetMentalModels(agentId: string): Promise<AgentView> {
  const { data } = await resetAgentMentalModels({
    path: { agent_id: agentId },
    throwOnError: true,
  });
  return data!;
}

/**
 * The fully composed system prompt an agent sends for one skill — soul, rules, mental
 * models, personality, task. Backend: GET /api/agents/:id/effective-prompt?key=…
 */
export async function getEffectivePrompt(
  agentId: string,
  key: string,
): Promise<EffectivePrompt> {
  const { data } = await agentEffectivePrompt({
    path: { agent_id: agentId },
    query: { key },
    throwOnError: true,
  });
  return data!;
}

/** All agent system prompts with their default + current text. Backend: GET /api/prompts */
export async function getPrompts(): Promise<PromptView[]> {
  if (USE_MOCK) return [];
  const { data } = await listPrompts({ throwOnError: true });
  return data ?? [];
}

/**
 * The generated client's `throwOnError` throws the parsed error *body*, not an Error, so
 * a FastAPI `detail` reaches a `catch (e as Error).message` as undefined. The console
 * shows that message inline, and for a rejected prompt save the detail is the whole point
 * — it names the placeholder that was dropped. Same preference as `errorMessage` in
 * client.ts.
 */
function sdkError(e: unknown, fallback: string): Error {
  const detail = (e as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail) return new Error(detail);
  if (e instanceof Error) return e;
  return new Error(fallback);
}

/** Override one prompt (takes effect on the next agent run). Backend: PUT /api/prompts/:key */
export async function savePrompt(key: string, text: string): Promise<PromptView> {
  try {
    const { data } = await updatePrompt({
      path: { key },
      body: { text },
      throwOnError: true,
    });
    return data!;
  } catch (e) {
    throw sdkError(e, `Could not save ${key}`);
  }
}

/** Reset one prompt to its built-in default. Backend: DELETE /api/prompts/:key */
export async function resetPromptToDefault(key: string): Promise<PromptView> {
  try {
    const { data } = await resetPrompt({ path: { key }, throwOnError: true });
    return data!;
  } catch (e) {
    throw sdkError(e, `Could not reset ${key}`);
  }
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

/* ============ Watchlist — per-ticker on/off toggle + delete ============ */

/** Persisted per-ticker overrides. Absence of an entry = tracked + enabled. Backend: GET /api/watchlists */
export function getWatchlistOverrides(): Promise<WatchlistEntry[]> {
  if (USE_MOCK) return mockResolve([]);
  return apiFetch<WatchlistEntry[]>("/api/watchlists");
}

/** Toggle scanning on/off for one ticker. Backend: PUT /api/watchlists/:ticker */
export function setWatchlistActive(ticker: string, active: boolean): Promise<WatchlistEntry> {
  if (USE_MOCK) return mockResolve({ ticker, enabled: active, deleted: false });
  return apiFetch<WatchlistEntry>(`/api/watchlists/${encodeURIComponent(ticker)}`, {
    method: "PUT",
    body: JSON.stringify({ enabled: active }),
  });
}

/** Remove a ticker from the watchlist completely (tombstone). Backend: DELETE /api/watchlists/:ticker */
export function deleteWatchlistItem(ticker: string): Promise<WatchlistEntry> {
  if (USE_MOCK) return mockResolve({ ticker, enabled: false, deleted: true });
  return apiFetch<WatchlistEntry>(`/api/watchlists/${encodeURIComponent(ticker)}`, {
    method: "DELETE",
  });
}

/**
 * Remove several tickers in one round trip. Backend: POST /api/watchlists/bulk-delete
 * (POST, not DELETE-with-body: the backend has no precedent for a body on DELETE.)
 */
export function bulkDeleteWatchlist(tickers: string[]): Promise<WatchlistEntry[]> {
  if (USE_MOCK) return mockResolve(tickers.map((ticker) => ({ ticker, enabled: false, deleted: true })));
  return apiFetch<WatchlistEntry[]>("/api/watchlists/bulk-delete", {
    method: "POST",
    body: JSON.stringify({ tickers }),
  });
}

/* ============ Sources → YouTube — channel subscriptions ============ */

/** Backend rows are snake_case; the rest of the app speaks camelCase. */
type RawChannel = {
  channel_id: string;
  handle?: string | null;
  name: string;
  thumbnail?: string | null;
  subscriber_count?: number | null;
  enabled: boolean;
  deleted: boolean;
  added_at?: string | null;
  last_polled_at?: string | null;
  last_error?: string | null;
  video_count: number;
};

type RawMatch = {
  video_url: string;
  video_id: string;
  channel_id: string;
  ticker: string;
  quote: string;
  timestamp_start?: number | null;
  relevance: number;
  title: string;
  channel_name?: string | null;
  published_at?: string | null;
  matched_at: string;
};

type RawReport = {
  channels: number;
  videos_seen: number;
  persisted: number;
  failed: number;
  matched: number;
  errors: string[];
};

function toChannel(r: RawChannel): YoutubeChannel {
  return {
    channelId: r.channel_id,
    handle: r.handle ?? undefined,
    name: r.name,
    thumbnail: r.thumbnail ?? undefined,
    subscriberCount: r.subscriber_count ?? undefined,
    enabled: r.enabled,
    deleted: r.deleted,
    addedAt: r.added_at ?? undefined,
    lastPolledAt: r.last_polled_at ?? undefined,
    lastError: r.last_error ?? undefined,
    videoCount: r.video_count,
  };
}

function toMatch(r: RawMatch): YoutubeMatch {
  return {
    videoUrl: r.video_url,
    videoId: r.video_id,
    channelId: r.channel_id,
    ticker: r.ticker,
    quote: r.quote,
    timestampStart: r.timestamp_start ?? undefined,
    relevance: r.relevance,
    title: r.title,
    channelName: r.channel_name ?? undefined,
    publishedAt: r.published_at ?? undefined,
    matchedAt: r.matched_at,
  };
}

/**
 * Map the backend's snake_case ingest report to camelCase.
 *
 * Exported because the streamed variant bypasses `apiFetch` entirely — `streamSse` hands
 * back the raw `result` frame, so the caller must map it here rather than trusting a
 * camelCase type annotation over snake_case data.
 */
export function toYoutubeIngestReport(r: RawReport): YoutubeIngestReport {
  return {
    channels: r.channels,
    videosSeen: r.videos_seen,
    persisted: r.persisted,
    failed: r.failed,
    matched: r.matched,
    errors: r.errors ?? [],
  };
}

/** Followed channels, newest first. Backend: GET /api/sources/youtube/channels */
export async function getYoutubeChannels(): Promise<YoutubeChannel[]> {
  if (USE_MOCK) return mockResolve(youtubeChannelsMock);
  const rows = await apiFetch<RawChannel[]>("/api/sources/youtube/channels");
  return rows.map(toChannel);
}

/**
 * Follow a channel. Returns as soon as it resolves — nothing is fetched yet.
 *
 * `id` is anything Supadata resolves — a URL, an @handle, or a UC… id. Pulling the videos
 * is a separate background job: stream {@link youtubeRefreshStreamPath} through
 * `runLiveJob`. Backend: POST /api/sources/youtube/channels
 */
export async function addYoutubeChannelSubscription(id: string): Promise<YoutubeChannel> {
  if (USE_MOCK) {
    return mockResolve({
      channelId: `UC${id}`,
      handle: id,
      name: id.replace(/^@/, ""),
      enabled: true,
      deleted: false,
      videoCount: 0,
    });
  }
  const raw = await apiFetch<RawChannel>("/api/sources/youtube/channels", {
    method: "POST",
    body: JSON.stringify({ id }),
  });
  return toChannel(raw);
}

/**
 * SSE path that ingests one channel's new videos, reporting progress as it goes.
 *
 * Ingest takes minutes per video, so it never runs inside a request. Feed this to
 * `runLiveJob` from the provider; the work continues server-side even if the stream drops.
 */
export function youtubeRefreshStreamPath(channelId: string, limit?: number): string {
  const qs = limit ? `?limit=${limit}` : "";
  return `/api/sources/youtube/channels/${encodeURIComponent(channelId)}/refresh/stream${qs}`;
}

/** Attach to a background job already in flight (after a reload). Backend: GET /api/jobs/:id/stream */
export function jobStreamPath(jobId: string): string {
  return `/api/jobs/${encodeURIComponent(jobId)}/stream`;
}

/** Ingests currently running, so a reloaded page can reattach. Backend: GET /api/sources/youtube/jobs */
export function getRunningYoutubeJobs(): Promise<YoutubeJobRef[]> {
  if (USE_MOCK) return mockResolve([]);
  return apiFetch<{ job_id: string; channel_id: string | null; status: string }[]>(
    "/api/sources/youtube/jobs",
  ).then((rows) =>
    rows.map((r) => ({ jobId: r.job_id, channelId: r.channel_id ?? undefined, status: r.status })),
  );
}

/** Pause or resume polling. Backend: PUT /api/sources/youtube/channels/:id */
export async function setYoutubeChannelEnabled(
  channelId: string,
  enabled: boolean,
): Promise<YoutubeChannel> {
  if (USE_MOCK) {
    const c = youtubeChannelsMock.find((x) => x.channelId === channelId)!;
    return mockResolve({ ...c, enabled });
  }
  const raw = await apiFetch<RawChannel>(
    `/api/sources/youtube/channels/${encodeURIComponent(channelId)}`,
    { method: "PUT", body: JSON.stringify({ enabled }) },
  );
  return toChannel(raw);
}

/** Unfollow a channel (tombstone). Backend: DELETE /api/sources/youtube/channels/:id */
export async function deleteYoutubeChannel(channelId: string): Promise<YoutubeChannel> {
  if (USE_MOCK) {
    const c = youtubeChannelsMock.find((x) => x.channelId === channelId)!;
    return mockResolve({ ...c, deleted: true, enabled: false });
  }
  const raw = await apiFetch<RawChannel>(
    `/api/sources/youtube/channels/${encodeURIComponent(channelId)}`,
    { method: "DELETE" },
  );
  return toChannel(raw);
}

/**
 * Watchlist moments found in followed channels' transcripts.
 * Backend: GET /api/sources/youtube/matches
 */
export async function getYoutubeMatches(opts?: {
  ticker?: string;
  channelId?: string;
  limit?: number;
}): Promise<YoutubeMatch[]> {
  if (USE_MOCK) {
    const all = youtubeMatchesMock;
    return mockResolve(opts?.ticker ? all.filter((m) => m.ticker === opts.ticker) : all);
  }
  const params = new URLSearchParams();
  if (opts?.ticker) params.set("ticker", opts.ticker);
  if (opts?.channelId) params.set("channel_id", opts.channelId);
  if (opts?.limit) params.set("limit", String(opts.limit));
  const qs = params.toString();
  const rows = await apiFetch<RawMatch[]>(
    `/api/sources/youtube/matches${qs ? `?${qs}` : ""}`,
  );
  return rows.map(toMatch);
}
