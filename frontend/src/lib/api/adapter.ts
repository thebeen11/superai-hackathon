/**
 * Backend → dashboard adapter.
 *
 * The backend implements only Layers 1–2 (Discovery + Data Engineering), so it
 * can fill the source-anchored slices of the dashboard from the persisted
 * `CleanedItem` rows: Sources, Trackers, Watchlist, Signal Volume, Indicators
 * (industry distribution), Sentiment (MACRO/MICRO mix), System health, Context
 * preview. Everything downstream that needs the agents themselves — the Bull/Bear
 * debate, prediction ledger, pending predictions, ACE index, chairman's briefing
 * and upcoming catalysts — comes from Tiers 3–5 (Andie / Freddy / Winston). Those
 * stay empty so the UI can show an explicit "awaiting Tier 3–5" state instead of
 * fabricated numbers.
 *
 * Thematic baskets are NOT part of this snapshot. They run weekly on their own
 * schedule and are read per-Run by the Thematic Analysis card — see
 * `thematicRunToThemes` below and `wtaf.ts`.
 *
 * In live mode the snapshot is built on top of `emptyLiveData` (NOT the mock), so
 * an empty database renders empty states rather than mock data. `wtafMock` is used
 * only offline (USE_MOCK / network error), handled in `wtaf.ts`.
 */
import type {
  Ace,
  BearSignposts,
  BriefingItem,
  BriefingTone,
  Catalyst,
  CatalystTone,
  ContextPreview,
  Debate,
  DebateTurn,
  DeskNote,
  Evidence,
  Indicator,
  IndicatorBand,
  IndicatorPoint,
  LedgerRow,
  Prediction,
  RiskBand,
  Signpost,
  SignpostStatus,
  Trend,
  Sentiment,
  Source,
  SourceDoc,
  SystemStatus,
  Theme,
  ThematicRunRef,
  Timeframe,
  Tier,
  Tracker,
  WatchItem,
  WatchlistEntry,
  WtafData,
} from "../types";
import { TIMEFRAMES } from "../types";
import { themeStance } from "../stance";
import { tierTopology } from "../tiers";
import type {
  CleanedItem,
  CouncilReport,
  DebateRecord as ApiDebateRecord,
  DebateTurn as ApiDebateTurn,
  Evidence as ApiEvidence,
  SourceRef as ApiSourceRef,
  ThematicRun,
} from "./generated/types.gen";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;
const MONTHS = [
  "JAN",
  "FEB",
  "MAR",
  "APR",
  "MAY",
  "JUN",
  "JUL",
  "AUG",
  "SEP",
  "OCT",
  "NOV",
  "DEC",
] as const;

/** Neutral live-mode base: every slice empty/neutral; tiers carry the real topology. */
export const emptyLiveData: WtafData = {
  now: "",
  marketOpen: false,
  ace: {
    value: 0,
    label: "—",
    delta: 0,
    components: [],
    overlay: { ace: [], smh: [] },
  },
  agents: [],
  tiers: tierTopology,
  debate: {
    topic: "",
    round: 0,
    rounds: 6,
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
  signalVolume: {
    title: "Signal Volume",
    sub: "items ingested",
    bars: [],
    peakLabel: "",
  },
  catalysts: [],
  system: { coverage: 0, bars: [] },
  trackers: [],
  contextPreview: {
    tracker: "",
    channel: "",
    sourceUrl: "",
    date: "",
    timestamp: "",
    quote: "",
    speaker: "",
    score: 0,
  },
  signposts: null,
  ledger: [],
  predictions: [],
  indicators: [],
  sources: [],
  sourceDocs: [],
  deskNotes: [],
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
    const k = dayKey(it.published_at ?? it.ingested_at);
    if (k) m.set(k, (m.get(k) ?? 0) + 1);
  }
  return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}

function deriveSources(items: CleanedItem[]): Source[] {
  const byHost = new Map<string, { kind: string; count: number }>();
  for (const it of items) {
    const name =
      it.source_type === "youtube" ? "YouTube" : hostOf(it.source_url);
    const kind = it.source_type === "youtube" ? "YouTube" : "Web";
    const cur = byHost.get(name) ?? { kind, count: 0 };
    cur.count += 1;
    byHost.set(name, cur);
  }
  return [...byHost.entries()]
    .map(([name, { kind, count }]) => ({
      name,
      kind,
      freq: "live",
      live: true,
      items: count,
    }))
    .sort((a, b) => b.items - a.items);
}

/** One row per document read — the audit ledger, keeping the URL that `deriveSources` drops. */
function deriveSourceDocs(items: CleanedItem[]): SourceDoc[] {
  return items.map((it) => ({
    url: it.source_url,
    title: it.title || it.source_url,
    kind: it.source_type === "youtube" ? "YouTube" : "Web",
    host: hostOf(it.source_url),
    author: it.author ?? undefined,
    publishedAt: it.published_at ?? it.ingested_at ?? undefined,
    stream: it.stream,
    themes: it.themes ?? [],
    tickers: (it.entities ?? [])
      .map((e) => e.canonical)
      .filter((c) => c.startsWith("$")),
    citedBy: [],
  }));
}

/**
 * A run's own source manifest → the document rows the UI renders.
 *
 * `deriveSourceDocs` reads the *live* corpus; this reads what one run actually read, with
 * the `cited_by` it was recorded with. For a run you can re-open weeks later that is the
 * honest ledger — the corpus underneath it has moved on since.
 */
export function sourceRefsToDocs(refs: ApiSourceRef[]): SourceDoc[] {
  return refs.map((s) => ({
    url: s.url,
    title: s.title || s.url,
    kind: s.source_type === "youtube" ? "YouTube" : "Web",
    host: hostOf(s.url),
    author: s.author ?? undefined,
    publishedAt: s.published_at ?? undefined,
    stream: s.stream,
    themes: s.themes ?? [],
    tickers: [],
    citedBy: s.cited_by ?? [],
  }));
}

/** Backend `Evidence` → frontend shape, keeping the timestamp the deep link needs. */
function evidenceOf(e: ApiEvidence): Evidence {
  return {
    quote: e.quote,
    sourceUrl: e.source_url,
    timestampStart: e.timestamp_start ?? undefined,
  };
}

export const evidenceList = (e: ApiEvidence[] | undefined | null): Evidence[] =>
  (e ?? []).map(evidenceOf);

/**
 * Concept trackers: one row per market theme Timo tagged.
 *
 * Volume (`mentions`/`spark`/`tone`) is counted here; *direction* is not derivable from
 * this side at all — a theme has no score in the corpus, and joining a theme to the
 * tickers that co-occur with it just re-reads whichever name dominates the crawl. So the
 * stance is Winston's own graded read on the fixed taxonomy, looked up by theme name
 * (`backend/app/council/theme_reads.py`), and a theme he never evidenced stays UNRATED.
 */
function deriveTrackers(
  items: CleanedItem[],
  council: CouncilReport | null | undefined,
): Tracker[] {
  // Common day axis across all items, so every tracker's sparkline shares one grid.
  const allDays = [
    ...new Set(
      items
        .map((it) => dayKey(it.published_at ?? it.ingested_at))
        .filter((k): k is string => !!k),
    ),
  ].sort();

  const reads = new Map(
    (council?.theme_reads ?? []).map((r) => [r.theme, r] as const),
  );

  const byTheme = new Map<
    string,
    { mentions: number; hosts: Set<string>; byDay: Map<string, number> }
  >();
  for (const it of items) {
    const host = hostOf(it.source_url);
    const day = dayKey(it.published_at ?? it.ingested_at);
    for (const theme of it.themes ?? []) {
      const cur = byTheme.get(theme) ?? {
        mentions: 0,
        hosts: new Set<string>(),
        byDay: new Map<string, number>(),
      };
      cur.mentions += 1;
      cur.hosts.add(host);
      if (day) cur.byDay.set(day, (cur.byDay.get(day) ?? 0) + 1);
      byTheme.set(theme, cur);
    }
  }
  const rows = [...byTheme.entries()].sort(
    (a, b) => b[1].mentions - a[1].mentions,
  );
  return rows.slice(0, 15).map(([name, { mentions, hosts, byDay }]) => {
    const read = reads.get(name);
    const stance = themeStance(read);
    // An unrated theme has no reason to show either — the card says so in its own words.
    const rationale = stance === "UNRATED" ? "" : read?.rationale ?? "";
    // Real per-day mention counts on the shared axis (zero-filled). Spark auto-normalizes.
    const series = allDays.map((day) => byDay.get(day) ?? 0);
    if (series.length < 2) {
      // Sparse history — pad to a flat 2-point line so the chart renders, not NaN.
      return {
        name,
        mentions,
        chg: 0,
        channels: hosts.size,
        spark: [mentions, mentions],
        tone: "flat" as const,
        stance,
        rationale,
      };
    }
    const mid = Math.floor(series.length / 2);
    const a = series.slice(0, mid).reduce((s, v) => s + v, 0);
    const b = series.slice(mid).reduce((s, v) => s + v, 0);
    const tone: Tracker["tone"] =
      b > a * 1.15 ? "up" : b < a * 0.85 ? "down" : "flat";
    return {
      name,
      mentions,
      chg: b - a,
      channels: hosts.size,
      spark: series,
      tone,
      stance,
      rationale,
    };
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

function deriveWatchlist(
  items: CleanedItem[],
  overrides: WatchlistEntry[] = [],
): WatchItem[] {
  // Persisted per-ticker state, keyed by upper-cased ticker (absence = tracked + enabled).
  const byTicker = new Map(overrides.map((o) => [o.ticker.toUpperCase(), o]));
  const rows = tickerCounts(items);
  const max = rows.length ? rows[0][1] : 1;
  return rows
    .map(([canonical, count]) => {
      const t = canonical.replace(/^\$/, "");
      const ov = byTicker.get(t.toUpperCase());
      return {
        t,
        n: canonical,
        px: 0, // no market-data tier yet
        chg: 0,
        alert: count > 1 ? `${count} mentions` : null,
        sig: Number((count / max).toFixed(2)),
        active: ov ? ov.enabled : true,
        _deleted: ov?.deleted ?? false,
      };
    })
    .filter((w) => !w._deleted) // tombstoned tickers leave the watchlist entirely
    .map(({ _deleted, ...w }) => w); // eslint-disable-line @typescript-eslint/no-unused-vars
}

function deriveSignalVolume(
  items: CleanedItem[],
): WtafData["signalVolume"] | null {
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
  return {
    title: "Signal Volume",
    sub: "items ingested",
    bars,
    peakLabel: `+${todayCount} today`,
  };
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
  const rows = [...byIndustry.entries()]
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, 6);
  if (rows.length === 0) return [];
  const max = rows[0][1].count;
  return rows.map(([name, { count, hosts }]) => {
    const score = Number((count / max).toFixed(2)); // 0..1 coverage strength
    return {
      name,
      score,
      band: score > 0.5 ? "Positive" : score > 0.2 ? "Neutral" : "Negative",
      rationale: `${count} item${count === 1 ? "" : "s"} · ${hosts.size} source${hosts.size === 1 ? "" : "s"}`,
      // Coverage heuristic, not an agent's read — there is no quote to cite until
      // Winston has scored the indicators himself.
      evidence: [],
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
  const mood =
    microShare > 0.6
      ? "RISK-ON"
      : microShare < 0.4
        ? "MACRO-DRIVEN"
        : "BALANCED";
  const moodTone = microShare > 0.6 ? "up" : microShare < 0.4 ? "down" : "flat";
  const counts = countsByDay(items).slice(-16);
  const maxDay = Math.max(1, ...counts.map(([, v]) => v));
  const wave = counts.map(([, v]) => clamp01(v / maxDay));
  return { mood, moodTone, vol: items.length > 40 ? "HIGH" : "LOW", wave };
}

function deriveSystem(items: CleanedItem[], sources: Source[]): SystemStatus {
  const latest = items
    .map((it) => new Date(it.published_at ?? it.ingested_at ?? 0).getTime())
    .filter((t) => t > 0);
  const minsAgo = latest.length
    ? Math.round((Date.now() - Math.max(...latest)) / 60000)
    : null;
  const freshTxt =
    minsAgo === null
      ? "—"
      : minsAgo < 60
        ? `${minsAgo} min ago`
        : `${Math.round(minsAgo / 60)}h ago`;
  const freshV = minsAgo === null ? 0 : clamp01(1 - minsAgo / (60 * 24)); // decays over a day
  return {
    coverage: clamp01(sources.length / 8),
    bars: [
      {
        k: "Sources live",
        v: clamp01(sources.length / 8),
        txt: `${sources.length}`,
      },
      {
        k: "Items stored",
        v: clamp01(items.length / 100),
        txt: `${items.length}`,
      },
      { k: "Freshness", v: freshV, txt: freshTxt },
    ],
  };
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

function deriveContextPreview(items: CleanedItem[]): ContextPreview | null {
  const withSegment = items.find((it) => (it.segments ?? []).length > 0);
  if (!withSegment) return null;
  const seg = withSegment.segments![0];
  const s = Math.floor(seg.start);
  const ts = withSegment.published_at ?? withSegment.ingested_at;
  const tracker = withSegment.themes?.[0] ?? withSegment.industry;
  // Snapshot fallback used only when the /api/trackers/:t/context endpoint is unavailable.
  // Derive an honest coverage score (share of items carrying this theme) instead of a
  // hardcoded placeholder, so it never shows a fake +0.00 / +0.50.
  const coverage =
    items.filter((it) => (it.themes ?? []).includes(tracker)).length /
    items.length;
  return {
    tracker,
    channel: hostOf(withSegment.source_url),
    sourceUrl: withSegment.source_url,
    date: ts ? new Date(ts).toISOString().slice(0, 10) : "",
    timestamp: `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`,
    timestampStart: seg.start,
    quote: `"${seg.text}"`,
    speaker:
      withSegment.source_type === "youtube" ? "Video transcript" : "Article",
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
const SIGNPOST_STATUSES: SignpostStatus[] = ["Triggered", "Watch", "Clear"];
const CATALYST_TONES: CatalystTone[] = ["orange", "blue", "green", "indigo"];

function asRisk(s?: string): RiskBand {
  const v = (s ?? "").trim().toLowerCase();
  if (v.startsWith("low")) return "Low";
  if (v.startsWith("high")) return "High";
  if (v.startsWith("med")) return "Med"; // med / medium
  return "Med";
}
function asBand(s?: string): IndicatorBand {
  return INDICATOR_BANDS.includes(s as IndicatorBand)
    ? (s as IndicatorBand)
    : "Neutral";
}
function asSignpostStatus(s?: string): SignpostStatus {
  return SIGNPOST_STATUSES.includes(s as SignpostStatus)
    ? (s as SignpostStatus)
    : "Clear";
}
function asBriefingTone(s?: string): BriefingTone {
  return s === "up" || s === "down" ? s : "neutral";
}
function asWho(s: string): DebateTurn["who"] {
  return s === "bull" || s === "bear" || s === "winston" ? s : "winston";
}

/** Snap a backend timeframe onto the closed set, mirroring the server-side normaliser. */
function asTimeframe(s: string | undefined): Timeframe {
  const found = TIMEFRAMES.find((t) => t.toLowerCase() === (s ?? "").trim().toLowerCase());
  return found ?? "Medium Term";
}

/** Winston's weekly baskets — the themes the Thematic Analysis card renders. */
export function thematicRunToThemes(run: ThematicRun): Theme[] {
  return (run.baskets ?? []).map((b) => ({
    name: b.name,
    risk: asRisk(b.risk),
    timeframe: asTimeframe(b.timeframe),
    horizon: b.horizon || "—",
    ret: 0, // no backtest tier yet — card shows it as pending
    stocks: b.stocks ?? [],
    strat: b.strat ?? "",
    conviction: clamp01(b.conviction ?? 0),
    verdict: b.verdict || undefined,
    hold: b.hold || undefined,
    evidence: evidenceList(b.evidence),
  }));
}

/**
 * Per-run indicator scores pivoted into one series per indicator, oldest point first.
 *
 * The backend sends a point per council run because that is how the runs are stored; the
 * cards read one indicator at a time. An indicator missing from a run contributes no
 * point to its series rather than a zero — a night Winston did not score it is a gap in
 * the line, not a reading of neutral.
 */
export function indicatorHistorySeries(
  points: { generated_at: string; scores?: { [k: string]: number } }[],
): Record<string, IndicatorPoint[]> {
  const series: Record<string, IndicatorPoint[]> = {};
  for (const p of points) {
    for (const [name, score] of Object.entries(p.scores ?? {})) {
      if (typeof score !== "number" || Number.isNaN(score)) continue;
      (series[name] ??= []).push({ at: p.generated_at, score });
    }
  }
  return series;
}

/** Run headers for the picker. `generated_at` is the backend's clock, never the client's. */
export function thematicRunRefs(
  rows: { id: number; generated_at: string; basket_count?: number }[],
): ThematicRunRef[] {
  return rows.map((r) => ({
    id: r.id,
    generatedAt: r.generated_at,
    basketCount: r.basket_count ?? 0,
  }));
}

/**
 * A backend `DebateRecord` as the Debate Chamber renders it.
 *
 * Shared by the council-wide debate on the snapshot and a single-ticker debate run, so
 * both chambers are one mapping — a ticker transcript that drifted from the council's
 * would render differently in the same card.
 */
export function debateRecordToDebate(d: ApiDebateRecord): Debate {
  return {
    topic: d.topic ?? "",
    round: d.round ?? 0,
    rounds: d.rounds ?? 6,
    bull: {
      name: d.bull.name,
      model: d.bull.model,
      accent: "green",
      stance: d.bull.stance ?? "",
    },
    bear: {
      name: d.bear.name,
      model: d.bear.model,
      accent: "red",
      stance: d.bear.stance ?? "",
    },
    verdict: d.verdict ?? "",
    transcript: (d.transcript ?? []).map(
      (t: ApiDebateTurn): DebateTurn => ({
        who: asWho(t.who),
        round: t.round,
        label: t.label,
        text: t.text,
      }),
    ),
  };
}

function councilDebate(report: CouncilReport): Debate | null {
  return report.debate ? debateRecordToDebate(report.debate) : null;
}

function councilIndicators(report: CouncilReport): Indicator[] {
  return (report.indicators ?? []).map((i) => ({
    name: i.name,
    score: i.score,
    band: asBand(i.band),
    rationale: i.rationale ?? "",
    evidence: evidenceList(i.evidence),
  }));
}

/** The Macro Analyst's bear-signpost tracker. The checklist is fixed backend-side,
 *  so the rows arrive complete and in order — pass them through untouched. */
function councilSignposts(report: CouncilReport): BearSignposts | null {
  const m = report.macro;
  if (!m || !m.signposts?.length) return null;
  const signposts: Signpost[] = m.signposts.map((s) => ({
    key: s.key,
    name: s.name,
    status: asSignpostStatus(s.status),
    rationale: s.rationale ?? "",
    evidence: evidenceList(s.evidence),
    evidenced: s.evidenced ?? true,
    backfilled: s.backfilled ?? false,
  }));
  return {
    signposts,
    triggered: m.triggered ?? 0,
    watch: m.watch ?? 0,
    total: m.total ?? signposts.length,
    riskScore: clamp01(m.risk_score ?? 0),
    label: m.label || "—",
    summary: m.summary ?? "",
  };
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
  return (report.briefing ?? []).map((b) => ({
    tone: asBriefingTone(b.tone),
    text: b.text,
    evidence: evidenceList(b.evidence),
  }));
}

function councilPredictions(report: CouncilReport): Prediction[] {
  return (report.predictions ?? []).map((p) => ({
    claim: p.claim,
    by: p.by,
    resolve: p.resolve,
    status: p.status ?? "pending",
    evidence: evidenceList(p.evidence),
  }));
}

function asTrend(s?: string): Trend {
  return s === "up" || s === "down" ? s : "flat";
}

/** The per-channel Brier ledger — Tier 3 rubric scoring (§7.3). */
function councilLedger(report: CouncilReport): LedgerRow[] {
  return (report.ledger ?? []).map((l) => ({
    rank: l.rank,
    name: l.name,
    acc: clamp01(l.acc),
    n: l.n,
    brier: clamp01(l.brier),
    trend: asTrend(l.trend),
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
  const mon = raw
    .toUpperCase()
    .match(/\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)/);
  return {
    d: day ? day[1].padStart(2, "0") : raw.slice(0, 5),
    m: mon ? mon[1] : "",
  };
}

/** Upcoming key events, derived from the Chairman's resolvable predictions. */
function councilCatalysts(report: CouncilReport): Catalyst[] {
  return (report.predictions ?? []).map((p, i) => {
    const { d, m } = splitResolve(p.resolve);
    return {
      d,
      m,
      t: p.claim,
      sub: `${p.by} · ${p.status ?? "pending"}`,
      tone: CATALYST_TONES[i % CATALYST_TONES.length],
    };
  });
}

/** Tier 3 desk notes — the per-ticker calls, each already grounded to a source. */
function councilDeskNotes(report: CouncilReport): DeskNote[] {
  return (report.sector_notes ?? []).map((n) => ({
    desk: n.desk,
    summary: n.summary ?? "",
    highlights: n.highlights ?? [],
    stocks: (n.stocks ?? []).map((s) => ({
      ticker: s.ticker,
      conviction: s.conviction,
      horizon: s.horizon,
      rationale: s.rationale ?? "",
      evidence: evidenceList(s.evidence),
    })),
  }));
}

/**
 * Tag each document with the agents that quoted it.
 *
 * Prefers the snapshot's own manifest, which records what that run actually read. Older
 * snapshots predate it, so fall back to joining every citation in the report by URL —
 * the ledger still shows "cited by" rather than going blank on historical data.
 */
function withCitations(
  docs: SourceDoc[],
  report: CouncilReport | null | undefined,
): SourceDoc[] {
  if (!report) return docs;

  const byUrl = new Map<string, string[]>();
  for (const s of report.sources ?? []) {
    if (s.cited_by?.length) byUrl.set(s.url, s.cited_by);
  }
  if (!byUrl.size) {
    const add = (url: string, agent: string) => {
      const cur = byUrl.get(url) ?? [];
      if (!cur.includes(agent)) byUrl.set(url, [...cur, agent]);
    };
    for (const n of report.sector_notes ?? [])
      for (const s of n.stocks ?? [])
        for (const e of s.evidence ?? []) add(e.source_url, `Andie-${n.desk}`);
    for (const s of report.macro?.signposts ?? [])
      for (const e of s.evidence ?? []) add(e.source_url, "Macro Analyst");
    for (const group of [
      report.indicators ?? [],
      report.baskets ?? [],
      report.briefing ?? [],
      report.predictions ?? [],
    ])
      for (const claim of group)
        for (const e of claim.evidence ?? []) add(e.source_url, "Winston");
  }

  return docs.map((d) => ({ ...d, citedBy: byUrl.get(d.url) ?? [] }));
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
          squad: t.squad.map((a) => ({
            ...a,
            status: "active",
            statusText: "online",
          })),
        },
  );
}

/** Map a persisted CouncilReport onto the Tier 3–5 slices of the dashboard. */
export function councilToWtafData(report: CouncilReport): Partial<WtafData> {
  const debate = councilDebate(report);
  const indicators = councilIndicators(report);
  const signposts = councilSignposts(report);
  const ace = councilAce(report);
  const briefing = councilBriefing(report);
  const predictions = councilPredictions(report);
  const ledger = councilLedger(report);
  const catalysts = councilCatalysts(report);
  const deskNotes = councilDeskNotes(report);
  return {
    tiers: activatedTiers(),
    ...(debate ? { debate } : {}),
    ...(indicators.length ? { indicators } : {}),
    ...(signposts ? { signposts } : {}),
    ...(ace ? { ace } : {}),
    ...(briefing.length ? { briefing } : {}),
    ...(predictions.length ? { predictions } : {}),
    ...(ledger.length ? { ledger } : {}),
    ...(catalysts.length ? { catalysts } : {}),
    ...(deskNotes.length ? { deskNotes } : {}),
  };
}

/**
 * Build the live snapshot from `emptyLiveData`, overriding each backend-derived
 * slice (only when non-empty, so cards fall back to their empty states). The Tier
 * 3–5 slices come from the council snapshot when one exists; otherwise they stay
 * empty and the cards show their "awaiting Tier 3–5" state.
 */
export function itemsToWtafData(
  items: CleanedItem[],
  council?: CouncilReport | null,
  watchlistOverrides: WatchlistEntry[] = [],
): WtafData {
  const sources = deriveSources(items);
  const sourceDocs = withCitations(deriveSourceDocs(items), council);
  const trackers = deriveTrackers(items, council);
  const watchlist = deriveWatchlist(items, watchlistOverrides);
  const signalVolume = deriveSignalVolume(items);
  const contextPreview = deriveContextPreview(items);
  const indicators = deriveIndicators(items);

  return {
    ...emptyLiveData,
    now: nowStamp(),
    // --- backend-backed (Layers 1–2), each guarded to keep empty states ---
    ...(sources.length ? { sources } : {}),
    ...(sourceDocs.length ? { sourceDocs } : {}),
    ...(trackers.length ? { trackers } : {}),
    ...(watchlist.length ? { watchlist } : {}),
    ...(signalVolume ? { signalVolume } : {}),
    ...(contextPreview ? { contextPreview } : {}),
    ...(indicators.length ? { indicators } : {}),
    sentiment: items.length ? deriveSentiment(items) : emptyLiveData.sentiment,
    system: items.length ? deriveSystem(items, sources) : emptyLiveData.system,
    // --- Tier 3–5 from the council snapshot (themes/indicators override the item
    //     heuristics; debate/briefing/ace/predictions/catalysts fill formerly-empty
    //     cards). Absent council → these stay empty and the cards show "awaiting". ---
    ...(council ? councilToWtafData(council) : {}),
  };
}
