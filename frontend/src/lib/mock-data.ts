/* ============ RAIJIN — mock data layer ============ */
import type { RaijinData } from "./types";

const sentimentWave = [
  0.42, 0.45, 0.5, 0.58, 0.55, 0.6, 0.72, 0.68, 0.74, 0.82, 0.78, 0.7, 0.66,
  0.71, 0.79, 0.86, 0.8, 0.74,
];

export const raijinMock: RaijinData = {
  now: "FRI 09 JUN 2026 · 14:21 ET",
  marketOpen: true,

  ace: {
    value: 0.34, // -1..+1
    label: "CAPITAL ABUNDANT",
    delta: +0.06,
    components: [
      { key: "AI Sentiment", weight: 0.4, score: 0.62 },
      { key: "Rate Expect.", weight: 0.3, score: 0.18 },
      { key: "Inflation Drag", weight: 0.3, score: 0.14 },
    ],
    overlay: {
      ace: [0.1, 0.14, 0.06, 0.18, 0.22, 0.16, 0.27, 0.31, 0.28, 0.34],
      smh: [0.05, 0.09, 0.04, 0.12, 0.2, 0.15, 0.24, 0.3, 0.26, 0.33],
    },
  },

  thesisCountdown: {
    label: "WEEKLY THESIS",
    sub: "Freddy · synthesis",
    target: "FRI 16:00",
    pct: 0.71,
  },

  agents: [
    {
      id: "wilfred",
      name: "Wilfred",
      role: "Scout · Ingestion",
      glyph: "W",
      accent: "blue",
      status: "active",
      statusText: "Transcribing 3 sources",
      queue: 4,
      throughput: "128 min/hr",
      tools: ["yt-dlp", "Whisper", "Playwright", "SEC EDGAR", "RSS"],
      skills: [
        "Top-down macro scan",
        "Bottom-up watchlist monitor",
        "Paywall auth",
      ],
      log: [
        "Fetched 2 videos · Macro Lens",
        "SEC 8-K · $NVDA queued",
        "RSS poll · 11 new items",
      ],
    },
    {
      id: "timo",
      name: "Timo",
      role: "Purifier · Pipeline",
      glyph: "T",
      accent: "indigo",
      status: "active",
      statusText: "Cleaning 2 transcripts",
      queue: 2,
      throughput: "1.2k chunks/hr",
      tools: ["SponsorBlock", "FinBERT NER", "LangChain", "Pinecone"],
      skills: ["Noise redaction", "Entity resolution", "Vector embedding"],
      log: [
        "Stripped 4 ad reads",
        'Resolved "J-Pow" → Federal Reserve',
        "Embedded 312 chunks",
      ],
    },
    {
      id: "andie",
      name: "Andie",
      role: "Brain · Analytics",
      glyph: "A",
      accent: "orange",
      status: "thinking",
      statusText: "Scoring 6 indicators",
      queue: 6,
      throughput: "48 scores/hr",
      tools: ["Claude Sonnet", "JSON Schema", "Vector Query"],
      skills: [
        "Semantic keyword tracker",
        "Rubric scoring",
        "Prediction ledger",
        "N-order thinking",
      ],
      log: [
        "Indicator · Rate Policy = +0.4",
        "Logged prediction · resolve 09/01",
        "3rd-order: capex → power demand",
      ],
    },
    {
      id: "freddy",
      name: "Freddy",
      role: "Allocator · Synthesis",
      glyph: "F",
      accent: "green",
      status: "idle",
      statusText: "Next thesis · Fri 16:00",
      queue: 0,
      throughput: "—",
      tools: ["Backtrader", "Polygon.io", "Pandas", "Reporting"],
      skills: ["ACE index", "Theme generator", "Backtest exec", "Weekly thesis"],
      log: [
        "Backtest · AI Buildout +31.4%",
        "Rebalanced 2 baskets",
        "Drafted 3-bullet brief",
      ],
    },
  ],

  briefing: [
    {
      tone: "up",
      text: "Dovish FOMC chatter accelerating — 4 of 6 tracked channels now flag a Sept cut as base case.",
    },
    {
      tone: "neutral",
      text: "AI data-centre capex theme remains the dominant signal; power & cooling names entering the conversation.",
    },
    {
      tone: "down",
      text: "2 pending predictions resolve this week — semis seasonality bear case still unconfirmed.",
    },
  ],

  watchlist: [
    { t: "NVDA", n: "NVIDIA", px: 1187.4, chg: +2.31, alert: "8-K filed", sig: +0.8 },
    { t: "AVGO", n: "Broadcom", px: 1642.0, chg: +1.08, alert: null, sig: +0.6 },
    { t: "VRT", n: "Vertiv", px: 112.7, chg: +3.94, alert: "3 mentions ↑", sig: +0.9 },
    { t: "AMD", n: "Adv. Micro", px: 168.2, chg: -0.72, alert: null, sig: +0.2 },
    { t: "SMCI", n: "Supermicro", px: 48.9, chg: -2.15, alert: "sentiment ↓", sig: -0.4 },
    { t: "MSFT", n: "Microsoft", px: 472.6, chg: +0.44, alert: null, sig: +0.5 },
  ],

  ticker: [
    { t: "$SMH", px: "278.42", chg: +1.62 },
    { t: "$QQQ", px: "511.08", chg: +0.74 },
    { t: "$NVDA", px: "1187.40", chg: +2.31 },
    { t: "$ARKK", px: "62.18", chg: -0.41 },
    { t: "$VRT", px: "112.70", chg: +3.94 },
    { t: "10Y", px: "4.12%", chg: -0.05 },
    { t: "$AVGO", px: "1642.00", chg: +1.08 },
    { t: "DXY", px: "103.8", chg: -0.22 },
    { t: "$SMCI", px: "48.90", chg: -2.15 },
    { t: "VIX", px: "13.4", chg: -0.6 },
    { t: "$AMD", px: "168.20", chg: -0.72 },
    { t: "$MSFT", px: "472.60", chg: +0.44 },
  ],

  sentiment: { mood: "RISK-ON", moodTone: "up", vol: "LOW", wave: sentimentWave },

  pipeline: [
    { stage: "Wilfred · Ingest", state: "done", detail: "14 sources synced" },
    { stage: "Timo · Purify", state: "done", detail: "9 transcripts cleaned" },
    { stage: "Andie · Analyze", state: "progress", detail: "6 indicators scoring" },
    { stage: "Freddy · Synthesize", state: "pending", detail: "thesis · Fri 16:00" },
  ],

  signalVolume: {
    title: "Signal Volume",
    sub: "transcripts processed",
    bars: [
      { d: "Mon", v: 0.55 },
      { d: "Tue", v: 0.62 },
      { d: "Wed", v: 0.48 },
      { d: "Thu", v: 0.7 },
      { d: "Fri", v: 0.9, peak: true },
      { d: "Sat", v: 0.34 },
      { d: "Sun", v: 0.4 },
    ],
    peakLabel: "+18 today",
  },

  catalysts: [
    { d: "10", m: "JUN", t: "CPI Print (May)", sub: "08:30 ET · consensus 3.2%", tone: "orange" },
    { d: "12", m: "JUN", t: "FOMC Rate Decision", sub: "14:00 ET · hold expected", tone: "blue" },
    { d: "13", m: "JUN", t: "$AVGO Earnings", sub: "after close · AI guide", tone: "green" },
    { d: "16", m: "JUN", t: "Weekly Thesis Drop", sub: "16:00 ET · Freddy", tone: "indigo" },
  ],

  system: {
    coverage: 0.92,
    bars: [
      { k: "Vector DB", v: 0.78, txt: "78%" },
      { k: "Sources live", v: 0.95, txt: "19/20" },
      { k: "Freshness", v: 0.88, txt: "4 min ago" },
    ],
  },

  trackers: [
    { name: "AI capex super-cycle", mentions: 142, chg: +34, channels: 8, spark: [0.3, 0.4, 0.35, 0.5, 0.62, 0.58, 0.7, 0.85, 0.9], tone: "up" },
    { name: "Rate cut · September", mentions: 96, chg: +22, channels: 6, spark: [0.2, 0.25, 0.3, 0.28, 0.4, 0.52, 0.6, 0.66, 0.74], tone: "up" },
    { name: "AI bubble / overvalued", mentions: 61, chg: -8, channels: 5, spark: [0.7, 0.66, 0.6, 0.55, 0.5, 0.46, 0.4, 0.38, 0.34], tone: "down" },
    { name: "Power & cooling demand", mentions: 48, chg: +19, channels: 4, spark: [0.1, 0.15, 0.2, 0.3, 0.36, 0.5, 0.58, 0.7, 0.8], tone: "up" },
    { name: "Consumer slowdown", mentions: 29, chg: +3, channels: 3, spark: [0.4, 0.42, 0.38, 0.44, 0.46, 0.43, 0.48, 0.5, 0.49], tone: "flat" },
  ],

  contextPreview: {
    tracker: "AI capex super-cycle",
    channel: "Silicon Signal",
    date: "08 JUN 2026",
    timestamp: "00:42:17",
    quote:
      '"The hyperscalers just told us capex is going up, not down — they are power-constrained, not demand-constrained. That re-rates the entire data-centre supply chain, cooling and electrical included."',
    speaker: "Host · earnings recap",
    score: +0.86,
  },

  themes: [
    {
      name: "AI Data-Centre Buildout",
      risk: "Med",
      horizon: "12M",
      ret: +31.4,
      stocks: ["NVDA", "AVGO", "VRT", "SMCI", "MSFT"],
      strat: "Own the power/cooling + compute supply chain feeding hyperscaler capex.",
      conviction: 0.82,
    },
    {
      name: "Disinflation Beneficiaries",
      risk: "Low",
      horizon: "6M",
      ret: +12.8,
      stocks: ["XLF", "KRE", "IWM"],
      strat: "Rate-sensitive small caps & banks on a confirmed Fed pivot.",
      conviction: 0.61,
    },
    {
      name: "Advanced Materials",
      risk: "High",
      horizon: "12M",
      ret: +9.2,
      stocks: ["MP", "ALB", "LAC"],
      strat: "Strategic minerals for grid + battery buildout. Volatile, policy-driven.",
      conviction: 0.48,
    },
  ],

  backtestThemes: [
    "AI Data-Centre Buildout",
    "Disinflation Beneficiaries",
    "Advanced Materials",
  ],

  ledger: [
    { rank: 1, name: "Silicon Signal", acc: 0.81, n: 42, brier: 0.14, trend: "up" },
    { rank: 2, name: "Macro Lens", acc: 0.74, n: 38, brier: 0.19, trend: "up" },
    { rank: 3, name: "Rate Watch", acc: 0.69, n: 51, brier: 0.22, trend: "flat" },
    { rank: 4, name: "Capital Currents", acc: 0.63, n: 29, brier: 0.27, trend: "down" },
    { rank: 5, name: "The Compound Daily", acc: 0.58, n: 33, brier: 0.31, trend: "up" },
  ],

  predictions: [
    { claim: "NVDA re-accelerates DC revenue QoQ", by: "Silicon Signal", resolve: "01 SEP", status: "pending" },
    { claim: "Fed cuts 25bps at Sept meeting", by: "Macro Lens", resolve: "18 SEP", status: "pending" },
    { claim: "CPI prints below 3.3% in May", by: "Rate Watch", resolve: "10 JUN", status: "pending" },
    { claim: "Semis correct >10% on seasonality", by: "Capital Currents", resolve: "01 AUG", status: "pending" },
  ],

  indicators: [
    { name: "Macro Outlook", score: +0.4, band: "Positive", evid: "4 channels · expansion language" },
    { name: "Inflation Traj.", score: +0.2, band: "Neutral", evid: "disinflation, sticky services" },
    { name: "Rate Policy", score: +0.5, band: "Positive", evid: "dovish FOMC commentary" },
    { name: "Market Sentiment", score: +0.6, band: "Positive", evid: "risk-on, AI leadership" },
    { name: "Sector Trends", score: +0.7, band: "Positive", evid: "semis + power broadening" },
    { name: "Geopolitical Risk", score: -0.3, band: "Negative", evid: "trade & export controls" },
  ],

  sources: [
    { name: "Silicon Signal", kind: "YouTube", freq: "daily", live: true, items: 42 },
    { name: "Macro Lens", kind: "YouTube", freq: "daily", live: true, items: 38 },
    { name: "Rate Watch", kind: "Podcast", freq: "weekly", live: true, items: 51 },
    { name: "Capital Currents", kind: "YouTube", freq: "daily", live: true, items: 29 },
    { name: "The Compound Daily", kind: "RSS", freq: "daily", live: true, items: 33 },
    { name: "SEC EDGAR", kind: "Filings", freq: "realtime", live: true, items: 118 },
    { name: "FedSpeak Wire", kind: "RSS", freq: "realtime", live: false, items: 0 },
  ],
};
