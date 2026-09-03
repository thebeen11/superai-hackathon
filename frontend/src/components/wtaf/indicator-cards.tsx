"use client";
/* ============ WTAF — Macro Indicator cards ============ */
import { useEffect, useId, useRef, useState } from "react";
import { getIndicatorHistory } from "@/lib/api/wtaf";
import { fmtRunDate } from "@/lib/format";
import type { Indicator, IndicatorPoint } from "@/lib/types";
import { useWtaf, useWtafData } from "@/providers/wtaf-provider";
import { Card, EmptyState } from "./primitives";
import { EvidenceList } from "./source-link";

const BAND_COLOR: Record<string, string> = {
  Positive: "var(--up)",
  Neutral: "var(--amber)",
  Negative: "var(--down)",
};

/** The score's own colour: above the zero line is constructive, below it is not. */
const scoreColor = (v: number) => (v >= 0 ? "var(--up)" : "var(--down)");

const fmtScore = (v: number, dp = 2) => `${v >= 0 ? "+" : ""}${v.toFixed(dp)}`;

/* --- the chart -------------------------------------------------------------
   Six of these render side by side, so they are small multiples of one measure and must
   share a scale: the axis is pinned to the full −1..+1 the backend scores on, never
   fitted to each indicator's own range. A line that looks flat here really is flat — a
   fitted axis would repaint a 0.05 drift as a cliff on one card and a shrug on the next,
   and the six stop being comparable. */

const H = 108;
const PAD = { t: 12, r: 10, b: 18, l: 26 };

/** Score → y. +1 at the top of the plot, −1 at the bottom, 0 on the baseline. */
const yOf = (score: number) =>
  PAD.t + ((1 - Math.max(-1, Math.min(1, score))) / 2) * (H - PAD.t - PAD.b);

/** Width isn't known until layout — the card is a fluid grid cell — so measure it. */
function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    setW(el.getBoundingClientRect().width);
    const ro = new ResizeObserver(([entry]) => setW(entry.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

/**
 * One indicator's score across past council runs.
 *
 * `points` is what the backend can actually date. When it is empty the chart still has
 * something true to show — `current`, the score on today's snapshot — and draws it as a
 * lone undated dot rather than inventing a past to run a line through.
 */
function ScoreTrend({ points, current }: { points: IndicatorPoint[]; current: number }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const fillId = "ind-fill-" + useId().replace(/:/g, "");

  const pts: IndicatorPoint[] = points.length ? points : [{ at: "", score: current }];
  const n = pts.length;
  const latest = pts[n - 1].score;
  const color = scoreColor(latest);
  const plotW = Math.max(0, w - PAD.l - PAD.r);
  // A single reading is centred rather than pinned to the left edge, so nothing about the
  // layout implies a direction it cannot support.
  const xOf = (i: number) => (n < 2 ? PAD.l + plotW / 2 : PAD.l + (i / (n - 1)) * plotW);

  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${xOf(i)} ${yOf(p.score)}`).join(" ");
  const area = `${line} L ${xOf(n - 1)} ${yOf(0)} L ${xOf(0)} ${yOf(0)} Z`;
  const active = hover === null ? null : pts[hover];

  return (
    <div ref={ref} style={{ position: "relative", width: "100%" }}>
      {w > 0 && (
        <svg
          width={w}
          height={H}
          role="img"
          aria-label={
            n > 1
              ? `Score over ${n} council runs, ${fmtRunDate(pts[0].at)} to ${fmtRunDate(pts[n - 1].at)}, latest ${fmtScore(latest)} on a −1 to +1 scale`
              : `Score ${fmtScore(latest)} on a −1 to +1 scale, one council run so far`
          }
          onPointerLeave={() => setHover(null)}
          style={{ display: "block", touchAction: "none" }}
        >
          <defs>
            <linearGradient id={fillId} x1="0" y1={latest >= 0 ? "0" : "1"} x2="0" y2={latest >= 0 ? "1" : "0"}>
              <stop offset="0%" stopColor={color} stopOpacity="0.24" />
              <stop offset="100%" stopColor={color} stopOpacity="0" />
            </linearGradient>
          </defs>

          {/* Axis: the two bounds and the zero line, all recessive. */}
          {[1, 0, -1].map((v) => (
            <g key={v}>
              <line
                x1={PAD.l} x2={w - PAD.r} y1={yOf(v)} y2={yOf(v)}
                stroke="var(--stroke)" strokeWidth={1}
                strokeDasharray={v === 0 ? undefined : "3 4"}
                opacity={v === 0 ? 1 : 0.6}
              />
              <text
                x={PAD.l - 6} y={yOf(v) + 3} textAnchor="end"
                className="mono" fontSize={8.5} fill="var(--t-faint)"
              >
                {v > 0 ? "+1" : v < 0 ? "−1" : "0"}
              </text>
            </g>
          ))}

          {n > 1 && (
            <>
              <path d={area} fill={`url(#${fillId})`} />
              <path d={line} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
            </>
          )}

          {/* Crosshair under the marks, so the hovered dot still reads on top. */}
          {hover !== null && (
            <line
              x1={xOf(hover)} x2={xOf(hover)} y1={PAD.t} y2={H - PAD.b}
              stroke={color} strokeWidth={1} opacity={0.45}
            />
          )}

          {pts.map((p, i) => {
            const big = hover === i || n === 1;
            return (
              <circle
                key={p.at + i}
                cx={xOf(i)} cy={yOf(p.score)}
                r={big ? 4 : 2.4}
                fill={color}
                stroke={big ? "var(--bg-1)" : "none"} strokeWidth={big ? 2 : 0}
              />
            );
          })}

          {/* Hit targets far wider than the dots they select. */}
          {pts.map((p, i) => (
            <rect
              key={"hit" + p.at + i}
              x={n < 2 ? PAD.l : xOf(i) - plotW / (2 * (n - 1))}
              y={0}
              width={n < 2 ? Math.max(plotW, 1) : plotW / (n - 1)}
              height={H - PAD.b}
              fill="transparent"
              onPointerEnter={() => setHover(i)}
            />
          ))}

          {/* Only the ends are dated — a label under every run would collide. */}
          {pts[0].at && (
            <text x={PAD.l} y={H - 5} className="mono" fontSize={9} fill="var(--t-faint)">
              {fmtRunDate(pts[0].at)}
            </text>
          )}
          {n > 1 && pts[n - 1].at && (
            <text x={w - PAD.r} y={H - 5} textAnchor="end" className="mono" fontSize={9} fill="var(--t-faint)">
              {fmtRunDate(pts[n - 1].at)}
            </text>
          )}
        </svg>
      )}

      {active?.at && (
        <div
          className="mono"
          style={{
            position: "absolute", top: 0, pointerEvents: "none",
            left: Math.min(Math.max(xOf(hover as number) - 46, 0), Math.max(0, w - 92)),
            width: 92, textAlign: "center", fontSize: 10,
            padding: "3px 0", borderRadius: 6,
            background: "var(--bg-1)", border: "1px solid var(--stroke-hi)",
            color: "var(--t-mid)", whiteSpace: "nowrap",
          }}
        >
          {fmtRunDate(active.at)} ·{" "}
          <span style={{ color: scoreColor(active.score) }}>{fmtScore(active.score)}</span>
        </div>
      )}
    </div>
  );
}

/* --- the cards -------------------------------------------------------------
   The history is fetched here rather than through the dashboard snapshot: these cards
   are its only reader and it only moves when the council runs, so every dashboard load
   should not pay for it (the same reasoning as the weekly thematic runs and the YouTube
   tab). If it never arrives, the card charts the score the snapshot already carries. */

export function IndicatorCards() {
  const d = useWtafData();
  const { discovering } = useWtaf();
  const [history, setHistory] = useState<Record<string, IndicatorPoint[]>>({});

  useEffect(() => {
    let alive = true;
    getIndicatorHistory()
      .then((h) => alive && setHistory(h))
      .catch(() => {}); // best-effort: the cards still chart the latest score
    return () => {
      alive = false;
    };
    // Re-read when a run ends, so a fresh council adds its point without a reload.
  }, [discovering]);

  if (d.indicators.length === 0) {
    return (
      <Card className="span12" loading={discovering}>
        <EmptyState label="No indicators yet" sub="Run a discovery to derive industry signals · rubric scores await Tier 3 (Andie)" />
      </Card>
    );
  }

  return (
    <>
      {d.indicators.map((ind: Indicator) => {
        const points = history[ind.name] ?? [];
        return (
          <Card
            key={ind.name}
            className="span4"
            title={ind.name}
            sub={points.length > 1 ? `${points.length} council runs` : "one run · no trend yet"}
          >
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10 }}>
              <div className="mono display" style={{ fontSize: 20, fontWeight: 700, color: scoreColor(ind.score), lineHeight: 1 }}>
                {fmtScore(ind.score, 1)}
              </div>
              <span className="chip" style={{ color: BAND_COLOR[ind.band], borderColor: `color-mix(in oklch, ${BAND_COLOR[ind.band]} 40%, transparent)` }}>{ind.band}</span>
            </div>
            <ScoreTrend points={points} current={ind.score} />
            <div style={{ fontSize: 11.5, color: "var(--t-lo)", marginTop: 4, lineHeight: 1.4, textWrap: "pretty" }}>{ind.rationale}</div>
            <EvidenceList items={ind.evidence} sources={d.sourceDocs} emptyLabel="not source-anchored" />
          </Card>
        );
      })}
    </>
  );
}
