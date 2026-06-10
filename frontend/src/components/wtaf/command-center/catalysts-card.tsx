"use client";
import type { Catalyst } from "@/lib/types";
import { Card, EmptyState } from "../primitives";

const MONTH_ORDER: Record<string, number> = {
  JAN: 0, FEB: 1, MAR: 2, APR: 3, MAY: 4, JUN: 5,
  JUL: 6, AUG: 7, SEP: 8, OCT: 9, NOV: 10, DEC: 11,
};

/** Earliest→latest span of the listed catalysts, formatted for the card label.
 *  Note: Catalyst carries no year, so a window crossing a year boundary
 *  (DEC→JAN) sorts the January entry as "earlier" — fine for this near-term card. */
function catalystWindow(catalysts: Catalyst[]): string {
  if (catalysts.length === 0) return "";
  const key = (c: Catalyst) => (MONTH_ORDER[c.m] ?? 0) * 100 + Number(c.d);
  let lo = catalysts[0];
  let hi = catalysts[0];
  for (const c of catalysts) {
    if (key(c) < key(lo)) lo = c;
    if (key(c) > key(hi)) hi = c;
  }
  if (lo === hi) return `${lo.m} ${lo.d}`;
  if (lo.m === hi.m) return `${lo.m} ${lo.d}–${hi.d}`;
  return `${lo.m} ${lo.d} – ${hi.m} ${hi.d}`;
}

export function CatalystsCard({ catalysts }: { catalysts: Catalyst[] }) {
  const window = catalystWindow(catalysts);
  const toneC: Record<string, string> = {
    orange: "var(--orange)",
    blue: "var(--blue-bright)",
    green: "var(--up)",
    indigo: "var(--indigo)",
  };
  return (
    <Card
      title="Upcoming Catalysts"
      sub="key events"
      className="span4"
      action={
        window ? (
          <span className="label-xs" style={{ fontSize: 9 }}>
            {window}
          </span>
        ) : undefined
      }
    >
      {catalysts.length === 0 ? (
        <EmptyState
          label="No catalysts scheduled"
          sub="Awaiting Tier 3–5 · Andie/Freddy/Winston"
        />
      ) : (
        <div style={{ display: "flex", flexDirection: "column" }}>
          {catalysts.map((c, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 13,
                padding: "9px 0",
                borderBottom:
                  i < catalysts.length - 1 ? "1px solid var(--stroke)" : "none",
              }}
            >
              <div style={{ textAlign: "center", width: 34, flexShrink: 0 }}>
                <div
                  className="mono display"
                  style={{
                    fontSize: 18,
                    fontWeight: 700,
                    lineHeight: 1,
                    color: "var(--t-hi)",
                  }}
                >
                  {c.d}
                </div>
                <div className="label-xs" style={{ fontSize: 8 }}>
                  {c.m}
                </div>
              </div>
              <div
                style={{
                  width: 2,
                  height: 26,
                  borderRadius: 2,
                  background: toneC[c.tone],
                  boxShadow: `0 0 8px ${toneC[c.tone]}`,
                }}
              />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12.5, fontWeight: 500 }}>{c.t}</div>
                <div
                  className="mono"
                  style={{ fontSize: 10.5, color: "var(--t-lo)", marginTop: 1 }}
                >
                  {c.sub}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
