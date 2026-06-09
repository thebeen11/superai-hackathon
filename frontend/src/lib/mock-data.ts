/* ============ WTAF — mock data layer ============ */
import type { WtafData } from "./types";

const sentimentWave = [
  0.42, 0.45, 0.5, 0.58, 0.55, 0.6, 0.72, 0.68, 0.74, 0.82, 0.78, 0.7, 0.66,
  0.71, 0.79, 0.86, 0.8, 0.74,
];

export const wtafMock: WtafData = {
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

  // ---- 5-tier Multi-Agent System (MapReduce fan-out → fan-in) ----
  tiers: [
    {
      n: 1, key: "discovery", label: "Discovery", sub: "fan-out · per channel", accent: "blue",
      status: "active", statusText: "14 sources syncing",
      squad: [
        { id: "wilfred-video", name: "Wilfred-Video", label: "Video", glyph: "WV", accent: "blue", role: "Discovery · YouTube / Audio", status: "active", statusText: "Transcribing 3 videos", queue: 4, throughput: "128 min/hr", tools: ["yt-dlp", "Whisper", "SponsorBlock"], skills: ["Audio ingestion", "Ad-read stripping", "Channel heartbeat"], log: ["Fetched 2 videos · Silicon Signal", "Whisper · 42 min transcribed", "SponsorBlock · 4 ads cut"] },
        { id: "wilfred-news", name: "Wilfred-News", label: "News", glyph: "WN", accent: "blue", role: "Discovery · Google / RSS", status: "active", statusText: "Polling 22 RSS feeds", queue: 6, throughput: "90 items/hr", tools: ["Google SERP", "RSS parsers", "Programmable Search"], skills: ["Headline scan", "Dedup & cluster", "Top-down macro sweep"], log: ["RSS poll · 11 new items", 'SERP · "Fed Sept cut" trending', "Clustered 6 duplicates"] },
        { id: "wilfred-premium", name: "Wilfred-Premium", label: "Premium", glyph: "WP", accent: "blue", role: "Discovery · Barron’s / WSJ", status: "thinking", statusText: "Auth Barron’s session", queue: 2, throughput: "40 art/hr", tools: ["Playwright", "Proxy rotation", "Anti-bot evasion"], skills: ["Paywall auth", "Columnist tracking", "Fault isolation"], log: ["Authenticated WSJ", "Pulled 2 Barron’s columns", "Proxy rotated · 1 retry"] },
      ],
    },
    {
      n: 2, key: "routing", label: "Engineering & Routing", sub: "Timo · semantic router", accent: "indigo",
      status: "active", statusText: "Tagging 312 chunks", bypass: true,
      squad: [
        { id: "timo", name: "Timo", label: "Router", glyph: "T", accent: "indigo", role: "Data Engineer · Semantic Router", status: "active", statusText: "Routing 312 chunks", queue: 312, throughput: "1.2k chunks/hr", tools: ["Llama-3 8B", "FinBERT NER", "Pinecone"], skills: ["MACRO / MICRO / INDUSTRY tagging", "Watchlist sector routing", "Time-decay TTL stamping", "Macro bypass → Winston"], log: ["Tagged 188 MICRO · 74 MACRO", "Routed AAPL supply-chain → Andie-Tech", "MACRO → Winston (bypass)"] },
      ],
    },
    {
      n: 3, key: "analysts", label: "Sector Analysts", sub: "fan-out · 20 stocks each", accent: "orange",
      status: "thinking", statusText: "3 desk notes scoring",
      squad: [
        { id: "andie-tech", name: "Andie-Tech", label: "TMT", glyph: "AT", accent: "orange", role: "Analyst · TMT (semis, software)", status: "thinking", statusText: "Scoring semis capex", queue: 20, throughput: "48 scores/hr", tools: ["Claude Sonnet", "Vector Query", "JSON Schema"], skills: ["Capex sensitivity", "Supply-chain reads", "Catalyst notes"], log: ["NVDA · DC re-accel flagged", "VRT · 3 power mentions", "Drafted TMT highlights note"] },
        { id: "andie-physical", name: "Andie-Physical", label: "Energy", glyph: "AP", accent: "orange", role: "Analyst · Energy / Industrials / Materials", status: "active", statusText: "Grading power demand", queue: 20, throughput: "44 scores/hr", tools: ["Claude Sonnet", "Vector Query", "JSON Schema"], skills: ["Commodity reads", "Grid-load sensitivity", "Regulation tracking"], log: ["Power & cooling demand +19", "Copper deficit · industry tag", "Drafted Physical note"] },
        { id: "andie-capital", name: "Andie-Capital", label: "Capital", glyph: "AC", accent: "orange", role: "Analyst · Financials / Consumer / RE", status: "idle", statusText: "Rate-sensitivity scan", queue: 20, throughput: "40 scores/hr", tools: ["Claude Sonnet", "Vector Query", "JSON Schema"], skills: ["Rate sensitivity", "Consumer credit reads", "Disinflation beneficiaries"], log: ["KRE · pivot beneficiary", "Consumer slowdown flat", "Drafted Capital note"] },
      ],
    },
    {
      n: 4, key: "debate", label: "Debate Chamber", sub: "adversarial · Bull vs Bear", accent: "amber",
      status: "active", statusText: "Round 2 of 3",
      squad: [
        { id: "freddy-bull", name: "Freddy-Bull", label: "Bull", glyph: "↑", accent: "green", role: "PM · Momentum bias · Claude Sonnet", status: "active", statusText: "Defending long thesis", queue: 0, throughput: "round 3", tools: ["Claude Sonnet", "Backtrader"], skills: ["Momentum theses", "Long construction", "Capex narrative"], log: ["R1 · proposed Memory basket", "Cited Andie-Tech capex note", "R3 · defending MU long"] },
        { id: "freddy-bear", name: "Freddy-Bear", label: "Bear", glyph: "↓", accent: "red", role: "PM · Risk bias · GPT-4o", status: "thinking", statusText: "Attacking valuation", queue: 0, throughput: "round 2", tools: ["GPT-4o", "Risk models"], skills: ["Risk attack", "Valuation critique", "Drawdown modeling"], log: ["R2 · MU overvalued", "Flagged capex slowdown H2", "Pushed half-position"] },
      ],
    },
    {
      n: 5, key: "chairman", label: "Chairman", sub: "fan-in · final judge", accent: "chair",
      status: "thinking", statusText: "Weighing verdict", bypassIn: true,
      squad: [
        { id: "winston", name: "Winston", label: "Chairman", glyph: "♔", accent: "chair", role: "Chairman · Judge & Allocator", status: "thinking", statusText: "Weighing Bull/Bear verdict", queue: 1, throughput: "Fri 16:00", tools: ["Claude Opus", "Macro Vector DB", "Reporting"], skills: ["Debate adjudication", "ACE index weighting", "Final allocation & hold periods", "Macro-regime sanity check"], log: ["Read debate transcript", "MU → half position", "ACE weights · AI 40 / rates 30 / infl 30"] },
      ],
    },
  ],

  debate: {
    topic: "Memory & AI-compute basket",
    round: 2, rounds: 3,
    bull: { name: "Freddy-Bull", model: "Claude Sonnet", accent: "green", stance: "Initiate 6-month long — MU, NVDA, AVGO ride the capex super-cycle; hyperscalers are power-constrained, not demand-constrained." },
    bear: { name: "Freddy-Bear", model: "GPT-4o", accent: "red", stance: "MU looks overvalued — Andie-Tech notes capex slowing into H2. Size half, hedge with a cooling-supplier pair." },
    verdict: "Bull thesis holds, but Bear’s valuation concern is valid — initiate a HALF position in MU, full weight in AVGO.",
    transcript: [
      { who: "bull", round: "R1", label: "Bull · proposes", text: "Across all three Andie desks the signal is one-directional: hyperscaler capex is going up, not down. I propose a Memory & AI-compute basket — MU, NVDA, AVGO — held ~6 months into the buildout." },
      { who: "bear", round: "R2", label: "Bear · attacks", text: "MU is the weak link. Andie-Tech’s own note flags capex pacing slowing into H2, and memory is the most cyclical name in the basket. At this multiple you’re buying peak earnings. Half-size it." },
      { who: "bull", round: "R3", label: "Bull · defends", text: "Fair on MU cyclicality — but AVGO’s custom-silicon backlog is contracted, not spot. I’ll concede a half-position on MU and keep AVGO at full weight; the power/cooling read from Andie-Physical de-risks the thesis." },
      { who: "winston", round: "Verdict", label: "Winston · rules", text: "Bull’s structural thesis holds and is corroborated by the macro bypass — disinflation + dovish Fed = abundant capital (ACE +0.34). Bear’s MU caution is valid. Verdict: half MU, full AVGO, starter NVDA. Re-evaluate at the Sept CPI print." },
    ],
  },

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
      text: "Debate chamber split on memory — Winston ruled half-size MU on Bear’s valuation flag; 2 predictions resolve this week.",
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
      verdict: "Bull holds — full weight",
      hold: "6–12M",
    },
    {
      name: "Disinflation Beneficiaries",
      risk: "Low",
      horizon: "6M",
      ret: +12.8,
      stocks: ["XLF", "KRE", "IWM"],
      strat: "Rate-sensitive small caps & banks on a confirmed Fed pivot.",
      conviction: 0.61,
      verdict: "Half-size — Bear rate risk",
      hold: "6M",
    },
    {
      name: "Advanced Materials",
      risk: "High",
      horizon: "12M",
      ret: +9.2,
      stocks: ["MP", "ALB", "LAC"],
      strat: "Strategic minerals for grid + battery buildout. Volatile, policy-driven.",
      conviction: 0.48,
      verdict: "Watch only — policy risk",
      hold: "12M",
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
