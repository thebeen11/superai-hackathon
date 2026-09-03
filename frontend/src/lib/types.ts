/* ============ WTAF — domain types ============ */

export type AccentKey = "blue" | "indigo" | "orange" | "green" | "red" | "amber" | "chair";
export type AgentStatus = "active" | "thinking" | "idle";
export type PipelineState = "done" | "progress" | "pending";
export type TrackerTone = "up" | "down" | "flat";
export type BriefingTone = "up" | "down" | "neutral";
export type CatalystTone = "orange" | "blue" | "green" | "indigo";
export type RiskBand = "Low" | "Med" | "High";
export type IndicatorBand = "Positive" | "Neutral" | "Negative";
export type SignpostStatus = "Triggered" | "Watch" | "Clear";
export type Trend = "up" | "down" | "flat";

export interface AceComponent {
  key: string;
  weight: number;
  score: number;
}
export interface Ace {
  value: number;
  label: string;
  delta: number;
  components: AceComponent[];
  overlay: { ace: number[]; smh: number[] };
}

export interface Agent {
  id: string;
  name: string;
  role: string;
  glyph: string;
  accent: AccentKey;
  status: AgentStatus;
  statusText: string;
  queue: number;
  throughput: string;
  tools: string[];
  skills: string[];
  log: string[];
  /** Short label used in the tier/squad flow (e.g. "TMT", "Bull"). */
  label?: string;
}

/* ---- Live agent activity (streamed from backend SSE progress) ---- */
export interface ActivityEntry {
  /** Stable React key, `${ts}-${seq}`. */
  id: string;
  /** Epoch seconds (from the progress frame, else client clock). */
  ts: number;
  /** Concrete agent id (e.g. "andie-tech") or null for council-wide / unrouted. */
  agentId: string | null;
  /** Display name, e.g. "Andie-TMT", "Timo", "Council". */
  agentName: string;
  /** Owning tier key, or null when unrouted. */
  tierKey: Tier["key"] | null;
  /** Human-readable line (the `[n/m]` prefix stripped). */
  message: string;
  /** Backend status: start | progress | ok | skip | error | info. */
  status: string;
  /** Raw progress stage (for filtering/debug). */
  stage: string;
}

/** Live status override for an agent, layered over its static snapshot status. */
export interface LiveAgentStatus {
  status: AgentStatus;
  statusText: string;
}

/* ---- 5-tier multi-agent system (fan-out → fan-in) ---- */
export interface Tier {
  n: number;
  key: "discovery" | "routing" | "analysts" | "debate" | "chairman";
  label: string;
  sub: string;
  accent: AccentKey;
  status: AgentStatus;
  statusText: string;
  bypass?: boolean;
  bypassIn?: boolean;
  squad: Agent[];
}

/* ---- Tier 4: Bull vs Bear debate ---- */
export interface DebateSide {
  name: string;
  model: string;
  accent: AccentKey;
  stance: string;
}
export interface DebateTurn {
  who: "bull" | "bear" | "winston";
  round: string;
  label: string;
  text: string;
}
export interface Debate {
  topic: string;
  round: number;
  rounds: number;
  bull: DebateSide;
  bear: DebateSide;
  verdict: string;
  transcript: DebateTurn[];
}

export interface BriefingItem {
  tone: BriefingTone;
  text: string;
  evidence: Evidence[];
}

export interface WatchItem {
  t: string;
  n: string;
  px: number;
  chg: number;
  alert: string | null;
  sig: number;
  active: boolean; // scanning on/off — false = paused (no new data pulled)
}

/** A persisted watchlist override (per-ticker). Absence = tracked + enabled. Backend: /api/watchlists */
export interface WatchlistEntry {
  ticker: string;
  enabled: boolean;
  deleted: boolean;
}

export interface TickerItem {
  t: string;
  px: string;
  chg: number;
}

export interface Sentiment {
  mood: string;
  moodTone: string;
  vol: string;
  wave: number[];
}

export interface PipelineStage {
  stage: string;
  state: PipelineState;
  detail: string;
}

export interface SignalBar {
  d: string;
  v: number;
  peak?: boolean;
}
export interface SignalVolume {
  title: string;
  sub: string;
  bars: SignalBar[];
  peakLabel: string;
}

export interface Catalyst {
  d: string;
  m: string;
  t: string;
  sub: string;
  tone: CatalystTone;
}

export interface SystemBar {
  k: string;
  v: number;
  txt: string;
}
export interface SystemStatus {
  coverage: number;
  bars: SystemBar[];
}

export interface Tracker {
  name: string;
  mentions: number;
  chg: number;
  channels: number;
  spark: number[];
  tone: TrackerTone;
}

export interface ContextPreview {
  tracker: string;
  channel: string;
  /** The item the quote came from — makes "Go to Source" a real link. */
  sourceUrl: string;
  date: string;
  timestamp: string;
  /** Seconds into a video, for a `?t=` deep link. Absent for articles. */
  timestampStart?: number;
  quote: string;
  speaker: string;
  score: number;
}

/** How long a theme's thesis needs to play out — the axis the card filters on. */
export type Timeframe = "Short Term" | "Medium Term" | "Long Term";

/** Human label for a timeframe, e.g. "Medium Term (1Q)". */
export const TIMEFRAME_LABEL: Record<Timeframe, string> = {
  "Short Term": "1M",
  "Medium Term": "1Q",
  "Long Term": "1Y",
};

export const TIMEFRAMES: Timeframe[] = ["Short Term", "Medium Term", "Long Term"];

export interface Theme {
  name: string;
  risk: RiskBand;
  timeframe: Timeframe;
  horizon: string;
  ret: number;
  stocks: string[];
  strat: string;
  conviction: number;
  /** Chairman's verdict + hold period (Winston, fan-in). */
  verdict?: string;
  hold?: string;
  evidence: Evidence[];
}

/** One dated Thematic Analysis run, as it appears in the card's run picker. */
export interface ThematicRunRef {
  id: number;
  /** ISO8601 UTC, from the backend — not the client clock. */
  generatedAt: string;
  basketCount: number;
}

/** One dated single-ticker debate, as the run picker on a ticker page lists it. */
export interface TickerDebateRunRef {
  id: number;
  ticker: string;
  /** ISO8601 UTC, from the backend — not the client clock. */
  generatedAt: string;
  turns: number;
}

export interface LedgerRow {
  rank: number;
  name: string;
  acc: number;
  n: number;
  brier: number;
  trend: Trend;
}

export interface Prediction {
  claim: string;
  by: string;
  resolve: string;
  status: string;
  evidence: Evidence[];
}

export interface Indicator {
  name: string;
  score: number;
  band: IndicatorBand;
  rationale: string;
  evidence: Evidence[];
}

/** One row of the Macro Analyst's fixed bear-market signpost checklist. */
export interface Signpost {
  key: string;
  name: string;
  status: SignpostStatus;
  rationale: string;
  evidence: Evidence[];
  /** false → nothing in the corpus spoke to it; the row renders dimmed, not green. */
  evidenced: boolean;
  /** true → graded on the Macro Analyst's second pass, from material fetched for this row
   *  rather than from the crawled corpus. Older snapshots simply don't carry it. */
  backfilled?: boolean;
}

/** A source-anchored quote backing any AI claim (no-orphan guardrail §12.6). */
export interface Evidence {
  quote: string;
  sourceUrl: string;
  /** Seconds into a video, so the link can open at the moment it was said. */
  timestampStart?: number;
}
/** @deprecated Use {@link Evidence} — kept so older call sites keep compiling. */
export type SignpostEvidence = Evidence;
export interface BearSignposts {
  signposts: Signpost[];
  triggered: number;
  watch: number;
  total: number;
  riskScore: number;
  label: string;
  summary: string;
}

/** A channel rollup for the Sources page summary (one row per host). */
export interface Source {
  name: string;
  kind: string;
  freq: string;
  live: boolean;
  items: number;
}

/**
 * A YouTube channel the Commander follows (Sources → YouTube).
 *
 * Unlike {@link Source}, which is derived from whatever the council happened to read, a
 * channel is a *standing* subscription: it keeps producing videos until it's paused.
 */
export interface YoutubeChannel {
  channelId: string;
  /** What the user typed when subscribing ("@Bloomberg", a URL, a UC… id). */
  handle?: string;
  name: string;
  thumbnail?: string;
  subscriberCount?: number;
  /** False = polling paused; the channel stays in the list. */
  enabled: boolean;
  deleted: boolean;
  addedAt?: string;
  lastPolledAt?: string;
  /** Last ingest failure, shown inline so a broken channel is never silently dead. */
  lastError?: string;
  /** Videos of this channel already ingested. */
  videoCount: number;
}

/** One moment in a video that discusses a watchlist ticker — YouTube's evidence unit. */
export interface YoutubeMatch {
  videoUrl: string;
  videoId: string;
  channelId: string;
  /** Canonical symbol, e.g. "$NVDA". */
  ticker: string;
  quote: string;
  /** Seconds into the video, so the link opens at the moment it was said. */
  timestampStart?: number;
  /** 0..1 — how squarely the moment is about the ticker, not just a name-drop. */
  relevance: number;
  title: string;
  channelName?: string;
  publishedAt?: string;
  matchedAt: string;
}

/** A background ingest in flight, so a reloaded page can reattach to its progress stream. */
export interface YoutubeJobRef {
  jobId: string;
  /** Undefined for a whole-poll job covering every channel. */
  channelId?: string;
  status: string;
}

/** What one channel ingest (or a whole poll) actually found. */
export interface YoutubeIngestReport {
  channels: number;
  videosSeen: number;
  persisted: number;
  failed: number;
  matched: number;
  errors: string[];
}

/** One document the council actually read — the auditable unit behind every claim. */
export interface SourceDoc {
  url: string;
  title: string;
  kind: string;
  host: string;
  author?: string;
  publishedAt?: string;
  stream: string;
  themes: string[];
  tickers: string[];
  /** Agents that quoted this document. Empty = read but nothing leaned on it. */
  citedBy: string[];
}

/** Tier 3 — one Andie desk's note, with the per-ticker calls it grounded. */
export interface DeskNote {
  desk: string;
  summary: string;
  highlights: string[];
  stocks: StockTake[];
}

export interface StockTake {
  ticker: string;
  conviction: number;
  horizon: string;
  rationale: string;
  evidence: Evidence[];
}

export interface WtafData {
  now: string;
  marketOpen: boolean;
  ace: Ace;
  agents: Agent[];
  tiers: Tier[];
  debate: Debate;
  briefing: BriefingItem[];
  watchlist: WatchItem[];
  ticker: TickerItem[];
  sentiment: Sentiment;
  pipeline: PipelineStage[];
  signalVolume: SignalVolume;
  catalysts: Catalyst[];
  system: SystemStatus;
  trackers: Tracker[];
  contextPreview: ContextPreview;
  ledger: LedgerRow[];
  predictions: Prediction[];
  indicators: Indicator[];
  /** null until the Macro Analyst has run (or on pre-existing snapshots). */
  signposts: BearSignposts | null;
  /** Channel rollup (one row per host). */
  sources: Source[];
  /** Every document read, one row each — the audit ledger behind the claims. */
  sourceDocs: SourceDoc[];
  /** Tier 3 desk notes, the origin of the per-ticker citations. */
  deskNotes: DeskNote[];
}
