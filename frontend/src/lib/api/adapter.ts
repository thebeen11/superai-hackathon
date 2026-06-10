/**
 * Backend → dashboard adapter.
 *
 * The backend implements only Layers 1–2 (Discovery + Data Engineering), so it
 * can fill the source-anchored slices of the dashboard from the persisted
 * `CleanedItem` rows: Sources, Trackers, Watchlist, Signal Volume, Indicators
 * (industry distribution), Sentiment (MACRO/MICRO mix), System health, Thematic
 * baskets (theme → tickers), Context preview. Everything downstream that needs
 * the agents themselves — the Bull/Bear debate, prediction ledger, pending
 * predictions, ACE index, chairman's briefing, upcoming catalysts, and the
 * conviction/return/verdict on baskets — comes from Tiers 3–5 (Andie / Freddy /
 * Winston), which are not built yet. Those stay empty so the UI can show an
 * explicit "awaiting Tier 3–5" state instead of fabricated numbers.
 *
 * In live mode the snapshot is built on top of `emptyLiveData` (NOT the mock), so
 * an empty database renders empty states rather than mock data. `wtafMock` is used
 * only offline (USE_MOCK / network error), handled in `wtaf.ts`.
 */
import type {
  Ace,
  BriefingItem,
  BriefingTone,
  Catalyst,
  CatalystTone,
  ContextPreview,
  Debate,
  DebateTurn,
  Indicator,
  IndicatorBand,
  Prediction,
  RiskBand,
  Sentiment,
  Source,
  SystemStatus,
  Theme,
  Tier,
  Tracker,
  WatchItem,
  WtafData,
} from "../types";
import { tierTopology } from "../tiers";
import type {
  CleanedItem,
  CouncilReport,
  DebateTurn as ApiDebateTurn,
} from "./generated/types.gen";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;
const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"] as const;

/** Neutral live-mode base: every slice empty/neutral; tiers carry the real topology. */
export const emptyLiveData: WtafData = {
  now: "",
  marketOpen: false,
  ace: { value: 0, label: "—", delta: 0, components: [], overlay: { ace: [], smh: [] } },
  agents: [],
  tiers: tierTopology,
  debate: {
    topic: "",
    round: 0,
    rounds: 3,
    bull: { name: "Freddy-Bull", model: "—", accent: "green", stance: "" },
    bear: { name: "Freddy-Bear", model: "—", accent: "red", stance: "" },
    verdict: "",
    transcript: [],
  },
  briefing: [],
  watchlist: [],
  ticker: [],
  sentiment: { mood: "—", moodTone: "flat", vol: "—", wave: [] },
  pipeline: [],
  signalVolume: { title: "Signal Volume", sub: "items ingested", bars: [], peakLabel: "" },
  catalysts: [],
  system: { coverage: 0, bars: [] },
  trackers: [],
  contextPreview: { tracker: "", channel: "", date: "", timestamp: "", quote: "", speaker: "", score: 0 },
  themes: [],
  backtestThemes: [],
  ledger: [],
  predictions: [],
  indicators: [],
  sources: [],
};

const clamp01 = (n: number) => Math.max(0, Math.min(1, n));

/** Hostname of a URL, stripped of a leading `www.` — used as a source name. */
function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "unknown";
  }
}

function dayKey(ts?: string | null): string | null {
  if (!ts) return null;
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? null : d.toISOString().slice(0, 10);
}

/** Counts per calendar day (chronological). */
function countsByDay(items: CleanedItem[]): [string, number][] {
  const m = new Map<string, number>();
  for (const it of items) {
    const k = dayKey(it.ingested_at ?? it.published_at);
    if (k) m.set(k, (m.get(k) ?? 0) + 1);
  }
  return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}

function deriveSources(items: CleanedItem[]): Source[] {
  const byHost = new Map<string, { kind: string; count: number }>();
  for (const it of items) {
    const name = it.source_type === "youtube" ? "YouTube" : hostOf(it.source_url);
    const kind = it.source_type === "youtube" ? "YouTube" : "Web";
    const cur = byHost.get(name) ?? { kind, count: 0 };
    cur.count += 1;
    byHost.set(name, cur);
  }
  return [...byHost.entries()]
    .map(([name, { kind, count }]) => ({ name, kind, freq: "live", live: true, items: count }))
    .sort((a, b) => b.items - a.items);
}

function deriveTrackers(items: CleanedItem[]): Tracker[] {
  // Common day axis across all items, so every tracker's sparkline shares one grid.
  const allDays = [...new Set(items.map((it) => dayKey(it.ingested_at ?? it.published_at)).filter((k): k is string => !!k))].sort();

  const byTheme = new Map<string, { mentions: number; hosts: Set<string>; byDay: Map<string, number> }>();
  for (const it of items) {
    const host = hostOf(it.source_url);
    const day = dayKey(it.ingested_at ?? it.published_at);
    for (const theme of it.themes ?? []) {
      const cur = byTheme.get(theme) ?? { mentions: 0, hosts: new Set<string>(), byDay: new Map<string, number>() };
      cur.mentions += 1;
      cur.hosts.add(host);
      if (day) cur.byDay.set(day, (cur.byDay.get(day) ?? 0) + 1);
      byTheme.set(theme, cur);
    }
  }
  const rows = [...byTheme.entries()].sort((a, b) => b[1].mentions - a[1].mentions);
  return rows.slice(0, 15).map(([name, { mentions, hosts, byDay }]) => {
    // Real per-day mention counts on the shared axis (zero-filled). Spark auto-normalizes.
    const series = allDays.map((day) => byDay.get(day) ?? 0);
    if (series.length < 2) {
      // Sparse history — pad to a flat 2-point line so the chart renders, not NaN.
      return { name, mentions, chg: 0, channels: hosts.size, spark: [mentions, mentions], tone: "flat" as const };
    }
    const mid = Math.floor(series.length / 2);
    const a = series.slice(0, mid).reduce((s, v) => s + v, 0);
    const b = series.slice(mid).reduce((s, v) => s + v, 0);
    const tone: Tracker["tone"] = b > a * 1.15 ? "up" : b < a * 0.85 ? "down" : "flat";
    return { name, mentions, chg: b - a, channels: hosts.size, spark: series, tone };
  });
}

/** Ticker → mention count, highest first (tickers only, macro entities skipped). */
function tickerCounts(items: CleanedItem[]): [string, number][] {
  const byTicker = new Map<string, number>();
  for (const it of items) {
    for (const ent of it.entities ?? []) {
      if (!ent.canonical.startsWith("$")) continue;
      byTicker.set(ent.canonical, (byTicker.get(ent.canonical) ?? 0) + 1);
    }
  }
  return [...byTicker.entries()].sort((a, b) => b[1] - a[1]);
}

function deriveWatchlist(items: CleanedItem[]): WatchItem[] {
  const rows = tickerCounts(items).slice(0, 8);
  const max = rows.length ? rows[0][1] : 1;
  return rows.map(([canonical, count]) => ({
    t: canonical.replace(/^\$/, ""),
    n: canonical,
    px: 0, // no market-data tier yet
    chg: 0,
    alert: count > 1 ? `${count} mentions` : null,
    sig: Number((count / max).toFixed(2)),
  }));
}

function deriveSignalVolume(items: CleanedItem[]): WtafData["signalVolume"] | null {
  const counts = countsByDay(items);
  if (counts.length === 0) return null;
  const days = counts.slice(-7);
  const max = Math.max(...days.map(([, v]) => v));
  const todayKey = new Date().toISOString().slice(0, 10);
  const bars = days.map(([key, v]) => ({
    d: WEEKDAYS[new Date(key).getUTCDay()],
    v: Number((v / max).toFixed(2)),
    peak: v === max,
  }));
  const todayCount = counts.find(([k]) => k === todayKey)?.[1] ?? 0;
  return { title: "Signal Volume", sub: "items ingested", bars, peakLabel: `+${todayCount} today` };
}

function deriveIndicators(items: CleanedItem[]): Indicator[] {
  const byIndustry = new Map<string, { count: number; hosts: Set<string> }>();
  for (const it of items) {
    const ind = it.industry || "Unclassified";
    if (ind === "Unclassified") continue;
    const cur = byIndustry.get(ind) ?? { count: 0, hosts: new Set<string>() };
    cur.count += 1;
    cur.hosts.add(hostOf(it.source_url));
    byIndustry.set(ind, cur);
  }
  const rows = [...byIndustry.entries()].sort((a, b) => b[1].count - a[1].count).slice(0, 6);
  if (rows.length === 0) return [];
  const max = rows[0][1].count;
  return rows.map(([name, { count, hosts }]) => {
    const score = Number((count / max).toFixed(2)); // 0..1 coverage strength
    return {
      name,
      score,
      band: score > 0.5 ? "Positive" : score > 0.2 ? "Neutral" : "Negative",
      evid: `${count} item${count === 1 ? "" : "s"} · ${hosts.size} source${hosts.size === 1 ? "" : "s"}`,
    };
  });
}

function deriveSentiment(items: CleanedItem[]): Sentiment {
  let micro = 0;
  let macro = 0;
  for (const it of items) {
    if (it.stream === "MICRO") micro += 1;
    else if (it.stream === "MACRO") macro += 1;
  }
  const total = micro + macro || 1;
  const microShare = micro / total;
  const mood = microShare > 0.6 ? "RISK-ON" : microShare < 0.4 ? "MACRO-DRIVEN" : "BALANCED";
  const moodTone = microShare > 0.6 ? "up" : microShare < 0.4 ? "down" : "flat";
  const counts = countsByDay(items).slice(-16);
  const maxDay = Math.max(1, ...counts.map(([, v]) => v));
  const wave = counts.map(([, v]) => clamp01(v / maxDay));
  return { mood, moodTone, vol: items.length > 40 ? "HIGH" : "LOW", wave };
}

function deriveSystem(items: CleanedItem[], sources: Source[]): SystemStatus {
  const latest = items
    .map((it) => new Date(it.ingested_at ?? it.published_at ?? 0).getTime())
    .filter((t) => t > 0);
  const minsAgo = latest.length ? Math.round((Date.now() - Math.max(...latest)) / 60000) : null;
  const freshTxt = minsAgo === null ? "—" : minsAgo < 60 ? `${minsAgo} min ago` : `${Math.round(minsAgo / 60)}h ago`;
  const freshV = minsAgo === null ? 0 : clamp01(1 - minsAgo / (60 * 24)); // decays over a day
  return {
    coverage: clamp01(sources.length / 8),
    bars: [
      { k: "Sources live", v: clamp01(sources.length / 8), txt: `${sources.length}` },
      { k: "Items stored", v: clamp01(items.length / 100), txt: `${items.length}` },
      { k: "Freshness", v: freshV, txt: freshTxt },
    ],
  };
}

function deriveThemes(items: CleanedItem[]): Theme[] {
  const byTheme = new Map<string, { count: number; tickers: Map<string, number>; hosts: Set<string> }>();
  for (const it of items) {
    const tickers = (it.entities ?? []).filter((e) => e.canonical.startsWith("$")).map((e) => e.canonical.replace(/^\$/, ""));
    for (const theme of it.themes ?? []) {
      const cur = byTheme.get(theme) ?? { count: 0, tickers: new Map<string, number>(), hosts: new Set<string>() };
      cur.count += 1;
      cur.hosts.add(hostOf(it.source_url));
      for (const tk of tickers) cur.tickers.set(tk, (cur.tickers.get(tk) ?? 0) + 1);
      byTheme.set(theme, cur);
    }
  }
  return [...byTheme.entries()]
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 6)
    .map(([name, { count, tickers, hosts }]) => ({
      name,
      risk: "Med" as const,
      horizon: "—",
      ret: 0, // backtest is Tier 5 — shown as pending in the card
      stocks: [...tickers.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([t]) => t),
      strat: `${count} item${count === 1 ? "" : "s"} across ${hosts.size} source${hosts.size === 1 ? "" : "s"}`,
      conviction: 0, // pending Chairman
      verdict: "Awaiting Chairman verdict",
      hold: "—",
    }));
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function deriveContextPreview(items: CleanedItem[]): ContextPreview | null {
  const withSegment = items.find((it) => (it.segments ?? []).length > 0);
  if (!withSegment) return null;
  const seg = withSegment.segments![0];
  const s = Math.floor(seg.start);
  const ts = withSegment.ingested_at ?? withSegment.published_at;
  const tracker = withSegment.themes?.[0] ?? withSegment.industry;
  // Snapshot fallback used only when the /api/trackers/:t/context endpoint is unavailable.
  // Derive an honest coverage score (share of items carrying this theme) instead of a
  // hardcoded placeholder, so it never shows a fake +0.00 / +0.50.
  const coverage = items.filter((it) => (it.themes ?? []).includes(tracker)).length / items.length;
  return {
    tracker,
    channel: hostOf(withSegment.source_url),
    date: ts ? new Date(ts).toISOString().slice(0, 10) : "",
    timestamp: `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`,
    quote: `"${seg.text}"`,
    speaker: withSegment.source_type === "youtube" ? "Video transcript" : "Article",
    score: Number(coverage.toFixed(2)),
  };
}

/** A human "FRI 09 JUN 2026 · 14:21" stamp from the client clock (set post-mount). */
function nowStamp(): string {
  const d = new Date();
  return `${WEEKDAYS[d.getDay()].toUpperCase()} ${pad(d.getDate())} ${MONTHS[d.getMonth()]} ${d.getFullYear()} · ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/* ============ Tier 3–5 (the Council) → dashboard ============ */

const INDICATOR_BANDS: IndicatorBand[] = ["Positive", "Neutral", "Negative"];
const CATALYST_TONES: CatalystTone[] = ["orange", "blue", "green", "indigo"];

function asRisk(s?: string): RiskBand {
  const v = (s ?? "").trim().toLowerCase();
  if (v.startsWith("low")) return "Low";
  if (v.startsWith("high")) return "High";
  if (v.startsWith("med")) return "Med"; // med / medium
  return "Med";
}
function asBand(s?: string): IndicatorBand {
  return INDICATOR_BANDS.includes(s as IndicatorBand) ? (s as IndicatorBand) : "Neutral";
}
function asBriefingTone(s?: string): BriefingTone {
  return s === "up" || s === "down" ? s : "neutral";
}
function asWho(s: string): DebateTurn["who"] {
  return s === "bull" || s === "bear" || s === "winston" ? s : "winston";
}

/** Winston's baskets are the real thematic portfolios — they replace the heuristic. */
function councilThemes(report: CouncilReport): Theme[] {
  return (report.baskets ?? []).map((b) => ({
    name: b.name,
    risk: asRisk(b.risk),
    horizon: b.horizon || "—",
    ret: 0, // no backtest tier yet — card shows it as pending
    stocks: b.stocks ?? [],
    strat: b.strat ?? "",
    conviction: clamp01(b.conviction ?? 0),
    verdict: b.verdict || undefined,
    hold: b.hold || undefined,
  }));
}

function councilDebate(report: CouncilReport): Debate | null {
  const d = report.debate;
  if (!d) return null;
  return {
    topic: d.topic ?? "",
    round: d.round ?? 0,
    rounds: d.rounds ?? 3,
    bull: { name: d.bull.name, model: d.bull.model, accent: "green", stance: d.bull.stance ?? "" },
    bear: { name: d.bear.name, model: d.bear.model, accent: "red", stance: d.bear.stance ?? "" },
    verdict: d.verdict ?? "",
    transcript: (d.transcript ?? []).map((t: ApiDebateTurn): DebateTurn => ({
      who: asWho(t.who),
      round: t.round,
      label: t.label,
      text: t.text,
    })),
  };
}

function councilIndicators(report: CouncilReport): Indicator[] {
  return (report.indicators ?? []).map((i) => ({
    name: i.name,
    score: i.score,
    band: asBand(i.band),
    evid: i.evidence ?? "",
  }));
}

function councilAce(report: CouncilReport): Ace | null {
  const a = report.ace;
  if (!a) return null;
  return {
    value: a.value,
    label: a.label,
    delta: a.delta ?? 0,
    components: a.components ?? [],
    overlay: { ace: [], smh: [] }, // no historical series; ACE card is not rendered
  };
}

function councilBriefing(report: CouncilReport): BriefingItem[] {
  return (report.briefing ?? []).map((b) => ({ tone: asBriefingTone(b.tone), text: b.text }));
}

function councilPredictions(report: CouncilReport): Prediction[] {
  return (report.predictions ?? []).map((p) => ({
    claim: p.claim,
    by: p.by,
    resolve: p.resolve,
    status: p.status ?? "pending",
  }));
}

/** Split a resolve date into a short day + month for the compact catalyst column.
 *  Handles ISO ("2025-12-15") and free-form ("15 DEC", "Dec 15") inputs. */
function splitResolve(resolve?: string): { d: string; m: string } {
  const raw = (resolve ?? "").trim();
  const iso = raw.match(/(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (iso) {
    const mi = Number(iso[2]) - 1;
    return { d: String(Number(iso[3])).padStart(2, "0"), m: MONTHS[mi] ?? "" };
  }
  const day = raw.match(/\b(\d{1,2})\b/);
  const mon = raw.toUpperCase().match(/\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)/);
  return { d: day ? day[1].padStart(2, "0") : raw.slice(0, 5), m: mon ? mon[1] : "" };
}

/** Upcoming key events, derived from the Chairman's resolvable predictions. */
function councilCatalysts(report: CouncilReport): Catalyst[] {
  return (report.predictions ?? []).map((p, i) => {
    const { d, m } = splitResolve(p.resolve);
    return {
      d,
      m,
      t: p.claim.length > 48 ? `${p.claim.slice(0, 47)}…` : p.claim,
      sub: `${p.by} · ${p.status ?? "pending"}`,
      tone: CATALYST_TONES[i % CATALYST_TONES.length],
    };
  });
}

/** Once the council has run, light up Tiers 3–5 in the agent-council flow. */
function activatedTiers(): Tier[] {
  return tierTopology.map((t) =>
    t.n < 3
      ? t
      : {
          ...t,
          status: "active",
          statusText: "online",
          squad: t.squad.map((a) => ({ ...a, status: "active", statusText: "online" })),
        },
  );
}

/** Map a persisted CouncilReport onto the Tier 3–5 slices of the dashboard. */
export function councilToWtafData(report: CouncilReport): Partial<WtafData> {
  const debate = councilDebate(report);
  const themes = councilThemes(report);
  const indicators = councilIndicators(report);
  const ace = councilAce(report);
  const briefing = councilBriefing(report);
  const predictions = councilPredictions(report);
  const catalysts = councilCatalysts(report);
  return {
    tiers: activatedTiers(),
    ...(debate ? { debate } : {}),
    ...(themes.length ? { themes } : {}),
    ...(indicators.length ? { indicators } : {}),
    ...(ace ? { ace } : {}),
    ...(briefing.length ? { briefing } : {}),
    ...(predictions.length ? { predictions } : {}),
    ...(catalysts.length ? { catalysts } : {}),
  };
}

/**
 * Build the live snapshot from `emptyLiveData`, overriding each backend-derived
 * slice (only when non-empty, so cards fall back to their empty states). The Tier
 * 3–5 slices come from the council snapshot when one exists; otherwise they stay
 * empty and the cards show their "awaiting Tier 3–5" state.
 */
export function itemsToWtafData(items: CleanedItem[], council?: CouncilReport | null): WtafData {
  const sources = deriveSources(items);
  const trackers = deriveTrackers(items);
  const watchlist = deriveWatchlist(items);
  const signalVolume = deriveSignalVolume(items);
  const contextPreview = deriveContextPreview(items);
  const indicators = deriveIndicators(items);
  const themes = deriveThemes(items);

  return {
    ...emptyLiveData,
    now: nowStamp(),
    // --- backend-backed (Layers 1–2), each guarded to keep empty states ---
    ...(sources.length ? { sources } : {}),
    ...(trackers.length ? { trackers } : {}),
    ...(watchlist.length ? { watchlist } : {}),
    ...(signalVolume ? { signalVolume } : {}),
    ...(contextPreview ? { contextPreview } : {}),
    ...(indicators.length ? { indicators } : {}),
    ...(themes.length ? { themes } : {}),
    sentiment: items.length ? deriveSentiment(items) : emptyLiveData.sentiment,
    system: items.length ? deriveSystem(items, sources) : emptyLiveData.system,
    // --- Tier 3–5 from the council snapshot (themes/indicators override the item
    //     heuristics; debate/briefing/ace/predictions/catalysts fill formerly-empty
    //     cards). Absent council → these stay empty and the cards show "awaiting". ---
    ...(council ? councilToWtafData(council) : {}),
  };
}
