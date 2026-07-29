"use client";
/* ============ WTAF — Predictions ============ */
import { useWtafData } from "@/providers/wtaf-provider";
import { Card, EmptyState } from "../primitives";
import { PageHead } from "../shared";
import { EvidenceList } from "../source-link";

export function PredictionsPage() {
  const d = useWtafData();

  return (
    <div>
      <PageHead
        title="Predictions"
        sub="prediction accuracy ledger · pending resolutions"
      />
      <div className="grid12">
        <Card
          title="Prediction Ledger"
          sub="channel accuracy · Brier-scored"
          className="span6"
        >
          {d.ledger.length === 0 ? (
            <EmptyState
              label="No prediction ledger yet"
              sub="Awaiting Tier 3 · Andie (rubric scoring)"
            />
          ) : (
            <>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "24px 1fr 56px 56px 50px",
                  gap: 8,
                  padding: "0 0 8px",
                  borderBottom: "1px solid var(--stroke)",
                }}
              >
                {["#", "Channel", "Acc", "Pred", "Brier"].map((h, i) => (
                  <span
                    key={i}
                    className="label-xs"
                    style={{
                      fontSize: 8.5,
                      textAlign: i > 1 ? "right" : "left",
                    }}
                  >
                    {h}
                  </span>
                ))}
              </div>
              {d.ledger.map((l, i) => (
                <div
                  key={i}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "24px 1fr 56px 56px 50px",
                    gap: 8,
                    alignItems: "center",
                    padding: "9px 0",
                    borderBottom:
                      i < d.ledger.length - 1
                        ? "1px solid var(--stroke)"
                        : "none",
                  }}
                >
                  <span
                    className="mono display"
                    style={{
                      fontSize: 13,
                      fontWeight: 700,
                      color: l.rank === 1 ? "var(--amber)" : "var(--t-lo)",
                    }}
                  >
                    {l.rank}
                  </span>
                  <span
                    style={{
                      fontSize: 12.5,
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    {l.name}
                    <span
                      style={{
                        fontSize: 9,
                        color:
                          l.trend === "up"
                            ? "var(--up)"
                            : l.trend === "down"
                              ? "var(--down)"
                              : "var(--t-faint)",
                      }}
                    >
                      {l.trend === "up" ? "▲" : l.trend === "down" ? "▼" : "—"}
                    </span>
                  </span>
                  <span
                    className="mono"
                    style={{
                      fontSize: 12,
                      textAlign: "right",
                      color: "var(--up)",
                    }}
                  >
                    {(l.acc * 100) | 0}%
                  </span>
                  <span
                    className="mono"
                    style={{
                      fontSize: 12,
                      textAlign: "right",
                      color: "var(--t-mid)",
                    }}
                  >
                    {l.n}
                  </span>
                  <span
                    className="mono"
                    style={{
                      fontSize: 11.5,
                      textAlign: "right",
                      color: "var(--t-lo)",
                    }}
                  >
                    {l.brier}
                  </span>
                </div>
              ))}
            </>
          )}
        </Card>

        <Card
          title="Pending Predictions"
          sub="awaiting resolution"
          className="span6"
        >
          {d.predictions.length === 0 ? (
            <EmptyState
              label="No pending predictions"
              sub="Awaiting Tier 3 · Andie (prediction ledger)"
            />
          ) : (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr",
                gap: 9,
              }}
            >
              {d.predictions.map((p, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    padding: "11px 13px",
                    borderRadius: 10,
                    background: "var(--inset)",
                    border: "1px solid var(--stroke)",
                  }}
                >
                  <span
                    style={{
                      width: 7,
                      height: 7,
                      borderRadius: 99,
                      background: "var(--amber)",
                      boxShadow: "0 0 7px var(--amber)",
                      flexShrink: 0,
                    }}
                  />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12.5 }}>{p.claim}</div>
                    <div
                      className="mono"
                      style={{
                        fontSize: 10,
                        color: "var(--t-lo)",
                        marginTop: 2,
                      }}
                    >
                      {p.by}
                    </div>
                    <EvidenceList items={p.evidence} sources={d.sourceDocs} />
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div
                      className="mono"
                      style={{ fontSize: 11.5, color: "var(--amber)" }}
                    >
                      {p.resolve}
                    </div>
                    <div className="label-xs" style={{ fontSize: 8 }}>
                      resolve by
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
