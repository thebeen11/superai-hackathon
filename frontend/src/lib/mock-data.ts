/* ============ WTAF — mock data layer ============ */
import type { WtafData, YoutubeChannel, YoutubeMatch } from "./types";

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
        { id: "freddy-bull", name: "Freddy-Bull", label: "Bull", glyph: "↑", accent: "green", role: "PM · Momentum bias · Claude Sonnet", status: "active", statusText: "Defending long thesis", queue: 0, throughput: "round 5", tools: ["Claude Sonnet", "Backtrader"], skills: ["Momentum theses", "Long construction", "Capex narrative"], log: ["R1 · proposed Memory basket", "R3 · conceded half MU", "R5 · final sizing set"] },
        { id: "freddy-bear", name: "Freddy-Bear", label: "Bear", glyph: "↓", accent: "red", role: "PM · Risk bias · GPT-4o", status: "thinking", statusText: "Attacking valuation", queue: 0, throughput: "round 6", tools: ["GPT-4o", "Risk models"], skills: ["Risk attack", "Valuation critique", "Drawdown modeling"], log: ["R2 · MU overvalued", "R4 · AVGO concentration risk", "R6 · single-factor warning"] },
      ],
    },
    {
      n: 5, key: "chairman", label: "Chairman", sub: "fan-in · final judge", accent: "chair",
      status: "thinking", statusText: "Weighing verdict", bypassIn: true,
      squad: [
        { id: "macro-analyst", name: "Macro Analyst", label: "Macro", glyph: "MA", accent: "amber", role: "Macro · Bear-signpost tracker (macro bypass)", status: "thinking", statusText: "Grading bear signposts", queue: 10, throughput: "10 signposts", tools: ["Gemini 3.1 Pro", "Macro Vector DB"], skills: ["Fixed signpost checklist", "Evidence grounding", "Cycle-risk composite"], log: ["Curve · inverted 14 months", "Breadth · 7 names carrying", "2/10 triggered · MID CYCLE"] },
        { id: "winston", name: "Winston", label: "Chairman", glyph: "♔", accent: "chair", role: "Chairman · Judge & Allocator", status: "thinking", statusText: "Weighing Bull/Bear verdict", queue: 1, throughput: "Fri 16:00", tools: ["Claude Opus", "Macro Vector DB", "Reporting"], skills: ["Debate adjudication", "ACE index weighting", "Final allocation & hold periods", "Macro-regime sanity check"], log: ["Read debate transcript", "MU → half position", "ACE weights · AI 40 / rates 30 / infl 30"] },
      ],
    },
  ],

  debate: {
    topic: "Memory & AI-compute basket",
    round: 6, rounds: 6,
    bull: { name: "Freddy-Bull", model: "Claude Sonnet", accent: "green", stance: "Initiate 6-month long — MU, NVDA, AVGO ride the capex super-cycle; hyperscalers are power-constrained, not demand-constrained." },
    bear: { name: "Freddy-Bear", model: "GPT-4o", accent: "red", stance: "MU looks overvalued — Andie-Tech notes capex slowing into H2. Size half, hedge with a cooling-supplier pair." },
    verdict: "Bull thesis holds, but Bear’s valuation concern is valid — initiate a HALF position in MU, full weight in AVGO.",
    transcript: [
      { who: "bull", round: "R1", label: "Bull · proposes", text: "Across all three Andie desks the signal is one-directional: hyperscaler capex is going up, not down. I propose a Memory & AI-compute basket — MU, NVDA, AVGO — held ~6 months into the buildout." },
      { who: "bear", round: "R2", label: "Bear · attacks", text: "MU is the weak link. Andie-Tech’s own note flags capex pacing slowing into H2, and memory is the most cyclical name in the basket. At this multiple you’re buying peak earnings. Half-size it." },
      { who: "bull", round: "R3", label: "Bull · defends", text: "Fair on MU cyclicality — but AVGO’s custom-silicon backlog is contracted, not spot. I’ll concede a half-position on MU and keep AVGO at full weight; the power/cooling read from Andie-Physical de-risks the thesis." },
      { who: "bear", round: "R4", label: "Bear · presses", text: "Then the basket rests entirely on AVGO’s backlog holding. That backlog is a customer concentration bet — two hyperscalers, both of whom have publicly floated in-housing their accelerators. The trigger that breaks this: one custom-silicon program slipping a quarter." },
      { who: "bull", round: "R5", label: "Bull · refines", text: "Accepted, and it’s sized for: half MU, full AVGO, starter NVDA as the liquid hedge on any single-program slip. Six-month hold, reviewed at the Sept CPI print and again on AVGO’s next backlog disclosure." },
      { who: "bear", round: "R6", label: "Bear · closes", text: "I’ll live with that sizing. The one thing to weigh: this whole basket is a single macro factor — capex. If the Fed turns and financing tightens, MU, AVGO and NVDA all draw down together. There is no diversification here, only conviction." },
      { who: "winston", round: "Verdict", label: "Winston · rules", text: "Bull’s structural thesis holds and is corroborated by the macro bypass — disinflation + dovish Fed = abundant capital (ACE +0.34). Bear’s MU caution is valid. Verdict: half MU, full AVGO, starter NVDA. Re-evaluate at the Sept CPI print." },
    ],
  },

  briefing: [
    {
      tone: "up",
      text: "Dovish FOMC chatter accelerating — 4 of 6 tracked channels now flag a Sept cut as base case.",
      evidence: [{ quote: "the balance sheet is still shrinking every month", sourceUrl: "https://example.com/macro-lens-qt" }],
    },
    {
      tone: "neutral",
      text: "AI data-centre capex theme remains the dominant signal; power & cooling names entering the conversation.",
      evidence: [{ quote: "they are power-constrained, not demand-constrained", sourceUrl: "https://www.youtube.com/watch?v=mockSilicon1", timestampStart: 2537 }],
    },
    {
      tone: "down",
      text: "Debate chamber split on memory — Winston ruled half-size MU on Bear’s valuation flag; 2 predictions resolve this week.",
      evidence: [],
    },
  ],

  watchlist: [
    { t: "NVDA", n: "NVIDIA", px: 1187.4, chg: +2.31, alert: "8-K filed", sig: +0.8, active: true },
    { t: "AVGO", n: "Broadcom", px: 1642.0, chg: +1.08, alert: null, sig: +0.6, active: true },
    { t: "VRT", n: "Vertiv", px: 112.7, chg: +3.94, alert: "3 mentions ↑", sig: +0.9, active: true },
    { t: "AMD", n: "Adv. Micro", px: 168.2, chg: -0.72, alert: null, sig: +0.2, active: true },
    { t: "SMCI", n: "Supermicro", px: 48.9, chg: -2.15, alert: "sentiment ↓", sig: -0.4, active: true },
    { t: "MSFT", n: "Microsoft", px: 472.6, chg: +0.44, alert: null, sig: +0.5, active: true },
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
    sourceUrl: "https://www.youtube.com/watch?v=mockSilicon1",
    timestamp: "00:42:17",
    timestampStart: 2537,
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
      evidence: [
        { quote: "they are power-constrained, not demand-constrained", sourceUrl: "https://www.youtube.com/watch?v=mockSilicon1", timestampStart: 2537 },
        { quote: "capex guidance went up across all four hyperscalers", sourceUrl: "https://example.com/compound-capex" },
      ],
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
      evidence: [{ quote: "core came in at three tenths, in line", sourceUrl: "https://example.com/rate-watch-cpi" }],
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
      evidence: [],
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
    { claim: "NVDA re-accelerates DC revenue QoQ", by: "Silicon Signal", resolve: "01 SEP", status: "pending", evidence: [{ quote: "they are power-constrained, not demand-constrained", sourceUrl: "https://www.youtube.com/watch?v=mockSilicon1", timestampStart: 2537 }] },
    { claim: "Fed cuts 25bps at Sept meeting", by: "Macro Lens", resolve: "18 SEP", status: "pending", evidence: [{ quote: "the balance sheet is still shrinking every month", sourceUrl: "https://example.com/macro-lens-qt" }] },
    { claim: "CPI prints below 3.3% in May", by: "Rate Watch", resolve: "10 JUN", status: "pending", evidence: [{ quote: "core came in at three tenths, in line", sourceUrl: "https://example.com/rate-watch-cpi" }] },
    { claim: "Semis correct >10% on seasonality", by: "Capital Currents", resolve: "01 AUG", status: "pending", evidence: [] },
  ],

  indicators: [
    { name: "Macro Outlook", score: +0.4, band: "Positive", rationale: "4 channels · expansion language", evidence: [{ quote: "ISM printed 51.4, the second month of expansion", sourceUrl: "https://example.com/rate-watch-ism" }] },
    { name: "Inflation Traj.", score: +0.2, band: "Neutral", rationale: "disinflation, sticky services", evidence: [{ quote: "core came in at three tenths, in line", sourceUrl: "https://example.com/rate-watch-cpi" }] },
    { name: "Rate Policy", score: +0.5, band: "Positive", rationale: "dovish FOMC commentary", evidence: [{ quote: "the balance sheet is still shrinking every month", sourceUrl: "https://example.com/macro-lens-qt" }] },
    { name: "Market Sentiment", score: +0.6, band: "Positive", rationale: "risk-on, AI leadership", evidence: [{ quote: "seven names are doing basically all of the work", sourceUrl: "https://example.com/compound-breadth" }] },
    { name: "Sector Trends", score: +0.7, band: "Positive", rationale: "semis + power broadening", evidence: [{ quote: "they are power-constrained, not demand-constrained", sourceUrl: "https://www.youtube.com/watch?v=mockSilicon1", timestampStart: 2537 }] },
    { name: "Geopolitical Risk", score: -0.3, band: "Negative", rationale: "trade & export controls", evidence: [] },
  ],

  // The Macro Analyst's fixed bear-signpost checklist (backend: taxonomy.BEAR_SIGNPOSTS).
  signposts: {
    triggered: 2,
    watch: 3,
    total: 10,
    riskScore: 0.35,
    label: "MID CYCLE · WATCH",
    summary:
      "Two signposts are lit — a still-inverted curve and narrow leadership — but credit and the labour market are holding. A widening in high-yield spreads would flip the picture.",
    signposts: [
      { key: "yield_curve", name: "Yield Curve", status: "Triggered", rationale: "2s10s inverted 14 months and only partly re-steepened", evidenced: true, evidence: [{ quote: "the curve has been inverted for fourteen months now", sourceUrl: "https://example.com/macro-lens-curve" }] },
      { key: "credit_spreads", name: "Credit Spreads", status: "Clear", rationale: "high-yield spreads still near cycle tights", evidenced: true, evidence: [{ quote: "high yield is not blinking at all here", sourceUrl: "https://example.com/rate-watch-credit" }] },
      { key: "unemployment", name: "Labour Market", status: "Watch", rationale: "claims drifting up, layoffs still concentrated in tech", evidenced: true, evidence: [{ quote: "continuing claims have been creeping higher for six weeks", sourceUrl: "https://example.com/macro-lens-jobs" }] },
      { key: "valuation", name: "Valuation", status: "Watch", rationale: "index multiple rich, equity risk premium thin", evidenced: true, evidence: [{ quote: "you are paying twenty two times for the index", sourceUrl: "https://example.com/capital-currents-valuation" }] },
      { key: "growth", name: "Growth Momentum", status: "Clear", rationale: "ISM back above 50 and rising", evidenced: true, evidence: [{ quote: "ISM printed 51.4, the second month of expansion", sourceUrl: "https://example.com/rate-watch-ism" }] },
      { key: "breadth", name: "Market Breadth", status: "Triggered", rationale: "equal-weight badly lagging cap-weight", evidenced: true, evidence: [{ quote: "seven names are doing basically all of the work", sourceUrl: "https://example.com/compound-breadth" }] },
      { key: "policy", name: "Policy & Liquidity", status: "Watch", rationale: "QT ongoing, real rates still restrictive", evidenced: true, evidence: [{ quote: "the balance sheet is still shrinking every month", sourceUrl: "https://example.com/macro-lens-qt" }] },
      { key: "inflation", name: "Inflation Re-acceleration", status: "Clear", rationale: "core still cooling, services sticky but not turning", evidenced: true, evidence: [{ quote: "core came in at three tenths, in line", sourceUrl: "https://example.com/rate-watch-cpi" }] },
      { key: "consumer", name: "Consumer Stress", status: "Clear", rationale: "Not evidenced in the current corpus.", evidenced: false, evidence: [] },
      { key: "sentiment", name: "Positioning & Euphoria", status: "Clear", rationale: "Not evidenced in the current corpus.", evidenced: false, evidence: [] },
    ],
  },

  sources: [
    { name: "Silicon Signal", kind: "YouTube", freq: "daily", live: true, items: 42 },
    { name: "Macro Lens", kind: "YouTube", freq: "daily", live: true, items: 38 },
    { name: "Rate Watch", kind: "Podcast", freq: "weekly", live: true, items: 51 },
    { name: "Capital Currents", kind: "YouTube", freq: "daily", live: true, items: 29 },
    { name: "The Compound Daily", kind: "RSS", freq: "daily", live: true, items: 33 },
    { name: "SEC EDGAR", kind: "Filings", freq: "realtime", live: true, items: 118 },
    { name: "FedSpeak Wire", kind: "RSS", freq: "realtime", live: false, items: 0 },
  ],

  // The audit ledger — every document read, with who quoted it. The YouTube row exists
  // so the `?t=` deep link is exercised in mock mode too.
  sourceDocs: [
    { url: "https://www.youtube.com/watch?v=mockSilicon1", title: "Hyperscaler capex recap: power, not demand", kind: "YouTube", host: "youtube.com", author: "Silicon Signal", publishedAt: "2026-07-24", stream: "MICRO", themes: ["AI Infrastructure", "Semiconductors"], tickers: ["$NVDA", "$VRT"], citedBy: ["Andie-TMT", "Winston"] },
    { url: "https://example.com/macro-lens-qt", title: "The balance sheet is still shrinking", kind: "Web", host: "example.com", author: "Macro Lens", publishedAt: "2026-07-23", stream: "MACRO", themes: ["Monetary Policy"], tickers: [], citedBy: ["Macro Analyst", "Winston"] },
    { url: "https://example.com/rate-watch-cpi", title: "Core CPI comes in at three tenths", kind: "Web", host: "example.com", author: "Rate Watch", publishedAt: "2026-07-22", stream: "MACRO", themes: ["Inflation"], tickers: [], citedBy: ["Macro Analyst", "Winston"] },
    { url: "https://example.com/rate-watch-ism", title: "ISM prints 51.4 — second month of expansion", kind: "Web", host: "example.com", author: "Rate Watch", publishedAt: "2026-07-21", stream: "MACRO", themes: ["Growth"], tickers: [], citedBy: ["Macro Analyst", "Winston"] },
    { url: "https://example.com/compound-breadth", title: "Seven names are doing all the work", kind: "Web", host: "example.com", author: "The Compound Daily", publishedAt: "2026-07-21", stream: "MACRO", themes: ["Market Breadth"], tickers: [], citedBy: ["Macro Analyst", "Winston"] },
    { url: "https://example.com/compound-capex", title: "Capex guidance rose across all four hyperscalers", kind: "Web", host: "example.com", author: "The Compound Daily", publishedAt: "2026-07-20", stream: "MICRO", themes: ["AI Infrastructure"], tickers: ["$MSFT"], citedBy: ["Winston"] },
    { url: "https://example.com/macro-lens-curve", title: "Fourteen months of curve inversion", kind: "Web", host: "example.com", author: "Macro Lens", publishedAt: "2026-07-19", stream: "MACRO", themes: ["Rates"], tickers: [], citedBy: ["Macro Analyst"] },
    { url: "https://example.com/macro-lens-jobs", title: "Continuing claims creep higher", kind: "Web", host: "example.com", author: "Macro Lens", publishedAt: "2026-07-18", stream: "MACRO", themes: ["Labour Market"], tickers: [], citedBy: ["Macro Analyst"] },
    { url: "https://example.com/rate-watch-credit", title: "High yield is not blinking", kind: "Web", host: "example.com", author: "Rate Watch", publishedAt: "2026-07-17", stream: "MACRO", themes: ["Credit"], tickers: [], citedBy: ["Macro Analyst"] },
    { url: "https://example.com/capital-currents-valuation", title: "Twenty-two times for the index", kind: "Web", host: "example.com", author: "Capital Currents", publishedAt: "2026-07-16", stream: "MACRO", themes: ["Valuation"], tickers: [], citedBy: ["Macro Analyst"] },
    // Read, but nothing in the report leaned on it — the ledger shows this rather than hiding it.
    { url: "https://example.com/capital-currents-seasonality", title: "August seasonality in semis", kind: "Web", host: "example.com", author: "Capital Currents", publishedAt: "2026-07-15", stream: "MICRO", themes: ["Semiconductors"], tickers: ["$AMD"], citedBy: [] },
  ],

  deskNotes: [
    {
      desk: "TMT",
      summary: "Power and cooling constraints are the binding limit on the AI buildout, not order books.",
      highlights: ["Hyperscaler capex revised up", "Grid interconnect queues lengthening"],
      stocks: [
        { ticker: "$NVDA", conviction: 0.78, horizon: "6-12M", rationale: "Demand visibility intact; supply is the constraint.", evidence: [{ quote: "they are power-constrained, not demand-constrained", sourceUrl: "https://www.youtube.com/watch?v=mockSilicon1", timestampStart: 2537 }] },
        { ticker: "$VRT", conviction: 0.64, horizon: "12M", rationale: "Cooling and electrical pull-through from the same capex.", evidence: [{ quote: "cooling and electrical included", sourceUrl: "https://www.youtube.com/watch?v=mockSilicon1", timestampStart: 2601 }] },
      ],
    },
  ],
};

/* ============ Sources → YouTube ============
 *
 * Kept out of `wtafMock` on purpose: the YouTube tab fetches its own data rather than
 * riding the global snapshot, so these are separate fixtures for the USE_MOCK path.
 */
export const youtubeChannelsMock: YoutubeChannel[] = [
  {
    channelId: "UCmockSilicon",
    handle: "@siliconsignals",
    name: "Silicon Signals",
    subscriberCount: 412000,
    enabled: true,
    deleted: false,
    addedAt: "2026-07-28T09:12:00Z",
    lastPolledAt: "2026-08-02T06:00:00Z",
    videoCount: 6,
  },
  {
    channelId: "UCmockMacro",
    handle: "@macrolens",
    name: "Macro Lens",
    subscriberCount: 88000,
    enabled: false,
    deleted: false,
    addedAt: "2026-07-30T15:40:00Z",
    lastPolledAt: "2026-08-01T18:00:00Z",
    videoCount: 3,
  },
];

export const youtubeMatchesMock: YoutubeMatch[] = [
  {
    videoUrl: "https://www.youtube.com/watch?v=mockSilicon1",
    videoId: "mockSilicon1",
    channelId: "UCmockSilicon",
    ticker: "$NVDA",
    quote: "they are power-constrained, not demand-constrained",
    timestampStart: 2537,
    relevance: 0.88,
    title: "The real bottleneck in the AI buildout",
    channelName: "Silicon Signals",
    publishedAt: "2026-08-01",
    matchedAt: "2026-08-01T12:00:00Z",
  },
  {
    videoUrl: "https://www.youtube.com/watch?v=mockSilicon1",
    videoId: "mockSilicon1",
    channelId: "UCmockSilicon",
    ticker: "$VRT",
    quote: "cooling and electrical included",
    timestampStart: 2601,
    relevance: 0.61,
    title: "The real bottleneck in the AI buildout",
    channelName: "Silicon Signals",
    publishedAt: "2026-08-01",
    matchedAt: "2026-08-01T12:00:00Z",
  },
];
