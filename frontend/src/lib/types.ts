/* ============ RAIJIN — domain types ============ */

export type AccentKey = "blue" | "indigo" | "orange" | "green" | "red";
export type AgentStatus = "active" | "thinking" | "idle";
export type PipelineState = "done" | "progress" | "pending";
export type TrackerTone = "up" | "down" | "flat";
export type BriefingTone = "up" | "down" | "neutral";
export type CatalystTone = "orange" | "blue" | "green" | "indigo";
export type RiskBand = "Low" | "Med" | "High";
export type IndicatorBand = "Positive" | "Neutral" | "Negative";
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

export interface ThesisCountdown {
  label: string;
  sub: string;
  target: string;
  pct: number;
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
}

export interface BriefingItem {
  tone: BriefingTone;
  text: string;
}

export interface WatchItem {
  t: string;
  n: string;
  px: number;
  chg: number;
  alert: string | null;
  sig: number;
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
  date: string;
  timestamp: string;
  quote: string;
  speaker: string;
  score: number;
}

export interface Theme {
  name: string;
  risk: RiskBand;
  horizon: string;
  ret: number;
  stocks: string[];
  strat: string;
  conviction: number;
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
}

export interface Indicator {
  name: string;
  score: number;
  band: IndicatorBand;
  evid: string;
}

export interface Source {
  name: string;
  kind: string;
  freq: string;
  live: boolean;
  items: number;
}

export interface RaijinData {
  now: string;
  marketOpen: boolean;
  ace: Ace;
  thesisCountdown: ThesisCountdown;
  agents: Agent[];
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
  themes: Theme[];
  backtestThemes: string[];
  ledger: LedgerRow[];
  predictions: Prediction[];
  indicators: Indicator[];
  sources: Source[];
}
