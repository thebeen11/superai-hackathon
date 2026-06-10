"use client";
/* ============ WTAF — primitives ============ */
import { useState, useEffect, useRef, useId, type ReactNode, type CSSProperties } from "react";
import type { AccentKey, SignalBar, TickerItem } from "@/lib/types";
import { ACCENTS } from "./accents";

export function Card({
  title,
  sub,
  action,
  children,
  className = "",
  pad = true,
  style,
  loading = false,
  updating = false,
}: {
  title?: string;
  sub?: string;
  action?: ReactNode;
  children?: ReactNode;
  className?: string;
  pad?: boolean;
  style?: CSSProperties;
  /** Discovery in progress and this region is empty → show a skeleton in the body. */
  loading?: boolean;
  /** Discovery in progress but this region already has data → keep it, flag "updating". */
  updating?: boolean;
}) {
  return (
    <div className={"card " + className} style={style}>
      {(title || action || updating) && (
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, padding: "15px 18px 0" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 9, minWidth: 0 }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, letterSpacing: "0.01em", color: "var(--t-hi)", whiteSpace: "nowrap", flexShrink: 0 }}>{title}</h3>
            {sub && <span className="mono" style={{ fontSize: 11, color: "var(--t-lo)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{sub}</span>}
            {updating && (
              <span className="mono" style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 10.5, color: "var(--blue-bright)", flexShrink: 0 }}>
                <Dot tone="blue" /> updating
              </span>
            )}
          </div>
          {action}
        </div>
      )}
      <div className={pad ? "card-pad" : ""} style={pad && title ? { paddingTop: 13 } : undefined}>
        {loading ? <CardSkeleton /> : children}
      </div>
    </div>
  );
}

/* loading placeholder shown inside a card while discovery streams (shimmer rows) */
export function CardSkeleton({ rows = 3, minHeight = 96 }: { rows?: number; minHeight?: number }) {
  const widths = ["100%", "82%", "92%", "70%", "88%"];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 11, minHeight, justifyContent: "center", padding: "2px 0" }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton-row" style={{ height: 13, borderRadius: 7, width: widths[i % widths.length] }} />
      ))}
    </div>
  );
}

/* empty / awaiting-data placeholder for a card or section */
export function EmptyState({ label, sub, minHeight = 96 }: { label: string; sub?: string; minHeight?: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 5, minHeight, textAlign: "center", padding: "14px 12px" }}>
      <div style={{ width: 30, height: 30, borderRadius: 9, display: "grid", placeItems: "center", border: "1px dashed var(--stroke-hi)", color: "var(--t-faint)", marginBottom: 4 }}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><circle cx="12" cy="12" r="9" /><path d="M12 8v4M12 16h.01" /></svg>
      </div>
      <div style={{ fontSize: 12.5, color: "var(--t-mid)", fontWeight: 500 }}>{label}</div>
      {sub && <div className="mono" style={{ fontSize: 10.5, color: "var(--t-faint)" }}>{sub}</div>}
    </div>
  );
}

/* signed delta pill */
export function Delta({ v, suffix = "%", size = 12 }: { v: number; suffix?: string; size?: number }) {
  const up = v >= 0;
  return (
    <span className="mono" style={{ color: up ? "var(--up)" : "var(--down)", fontSize: size, fontWeight: 600 }}>
      {up ? "▲" : "▼"} {up ? "+" : ""}{v.toFixed(2)}{suffix}
    </span>
  );
}

/* circular progress ring with gradient + glow; children = center */
export function Ring({
  value,
  size = 150,
  stroke = 11,
  from = "blue",
  to = "indigo",
  track = "rgba(255,255,255,0.07)",
  children,
  glow = true,
  gap = 0,
}: {
  value: number;
  size?: number;
  stroke?: number;
  from?: AccentKey;
  to?: AccentKey;
  track?: string;
  children?: ReactNode;
  glow?: boolean;
  gap?: number;
}) {
  const id = "rg" + useId().replace(/:/g, "");
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const span = 1 - gap;
  const off = c * (1 - Math.max(0, Math.min(1, value)) * span);
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={ACCENTS[from].g} />
            <stop offset="100%" stopColor={ACCENTS[to].c} />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={track} strokeWidth={stroke} strokeDasharray={gap ? `${c * span} ${c * gap}` : undefined} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={`url(#${id})`}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={off}
          style={{ transition: "stroke-dashoffset 1.1s cubic-bezier(.2,.7,.2,1)", filter: glow ? `drop-shadow(0 0 7px ${ACCENTS[to].c})` : "none" }}
        />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center" }}>{children}</div>
    </div>
  );
}

/* vertical bar chart, gradient bars, optional peak tooltip */
export function BarChart({ bars, height = 136, peakLabel }: { bars: SignalBar[]; height?: number; peakLabel?: string }) {
  const innerH = height - 30;
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 10, height, position: "relative" }}>
      {bars.map((b, i) => (
        <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 8, height: "100%", justifyContent: "flex-end", position: "relative" }}>
          {b.peak && peakLabel && (
            <div className="mono" style={{ position: "absolute", top: -2, fontSize: 10.5, fontWeight: 600, color: "var(--t-hi)", background: "var(--panel-hi)", border: "1px solid var(--stroke-hi)", borderRadius: 6, padding: "2px 6px", whiteSpace: "nowrap" }}>{peakLabel}</div>
          )}
          <div style={{
            width: 15, height: Math.max(8, b.v * innerH), minHeight: Math.max(8, b.v * innerH), borderRadius: 7, flexShrink: 0,
            transformOrigin: "bottom", animation: `grow-bar .55s ${i * 0.05}s both cubic-bezier(.2,.7,.2,1)`,
            background: b.peak ? "linear-gradient(180deg, var(--blue-bright), var(--indigo))" : "linear-gradient(180deg, oklch(0.82 0.13 222), oklch(0.6 0.18 268))",
            boxShadow: b.peak ? "0 0 16px -1px var(--blue-bright)" : "0 0 10px -3px oklch(0.74 0.15 240)",
          }} />
          <span className="mono" style={{ fontSize: 10.5, color: b.peak ? "var(--t-hi)" : "var(--t-lo)", fontWeight: b.peak ? 600 : 400 }}>{b.d}</span>
        </div>
      ))}
    </div>
  );
}

/* smooth line/area path generator */
export function smoothPath(pts: [number, number][]): string {
  if (pts.length < 2) return "";
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const [x0, y0] = pts[i];
    const [x1, y1] = pts[i + 1];
    const cx = (x0 + x1) / 2;
    d += ` C ${cx} ${y0}, ${cx} ${y1}, ${x1} ${y1}`;
  }
  return d;
}

/* sparkline / waveform with glow + optional area fill + draw animation */
export function Spark({
  data,
  w = 240,
  h = 60,
  color = "var(--blue-bright)",
  fill = false,
  strokeW = 2.2,
  animate = true,
  pad = 4,
}: {
  data: number[];
  w?: number;
  h?: number;
  color?: string;
  fill?: boolean;
  strokeW?: number;
  animate?: boolean;
  pad?: number;
}) {
  const id = "sp" + useId().replace(/:/g, "");
  const min = Math.min(...data), max = Math.max(...data);
  const rng = max - min || 1;
  const pts = data.map((v, i): [number, number] => [pad + (i / (data.length - 1)) * (w - pad * 2), h - pad - ((v - min) / rng) * (h - pad * 2)]);
  const line = smoothPath(pts);
  const area = `${line} L ${pts[pts.length - 1][0]} ${h} L ${pts[0][0]} ${h} Z`;
  const pathRef = useRef<SVGPathElement>(null);
  const [len, setLen] = useState(0);
  useEffect(() => { if (pathRef.current) setLen(pathRef.current.getTotalLength()); }, [w, h]);
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill && <path d={area} fill={`url(#${id})`} />}
      <path
        ref={pathRef}
        d={line}
        fill="none"
        stroke={color}
        strokeWidth={strokeW}
        strokeLinecap="round"
        style={{
          filter: `drop-shadow(0 0 5px ${color})`,
          strokeDasharray: animate ? len : undefined,
          strokeDashoffset: animate ? 0 : undefined,
          ["--len" as string]: len,
          animation: animate && len ? "draw-line 1.3s ease forwards" : undefined,
        } as CSSProperties}
      />
    </svg>
  );
}

/* live status dot */
export function Dot({ tone = "blue", pulse = true }: { tone?: string; pulse?: boolean }) {
  const c = ACCENTS[tone as AccentKey] ? ACCENTS[tone as AccentKey].c : tone;
  return (
    <span style={{ width: 7, height: 7, borderRadius: 99, background: c, boxShadow: `0 0 8px ${c}`, display: "inline-block", animation: pulse ? "pulse-dot 1.6s infinite" : "none", flexShrink: 0 }} />
  );
}

/* horizontal mini progress bar */
export function MiniBar({ v, color = "var(--blue-bright)", h = 5 }: { v: number; color?: string; h?: number }) {
  return (
    <div style={{ height: h, background: "rgba(255,255,255,0.07)", borderRadius: 99, overflow: "hidden", flex: 1 }}>
      <div style={{ width: `${v * 100}%`, height: "100%", borderRadius: 99, background: `linear-gradient(90deg, ${color}, var(--blue))`, boxShadow: `0 0 8px -1px ${color}` }} />
    </div>
  );
}

/* scrolling ticker tape */
export function TickerTape({ items }: { items: TickerItem[] }) {
  const row = [...items, ...items];
  return (
    <div style={{ overflow: "hidden", flex: 1, maskImage: "linear-gradient(90deg, transparent, #000 4%, #000 96%, transparent)" }}>
      <div style={{ display: "inline-flex", gap: 26, whiteSpace: "nowrap", animation: "marquee 38s linear infinite" }}>
        {row.map((it, i) => (
          <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
            <span style={{ color: "var(--t-mid)", fontWeight: 600 }}>{it.t}</span>
            <span className="mono" style={{ color: "var(--t-hi)" }}>{it.px}</span>
            <span className="mono" style={{ color: it.chg >= 0 ? "var(--up)" : "var(--down)", fontSize: 11.5 }}>
              {it.chg >= 0 ? "+" : ""}{it.chg.toFixed(2)}%
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
