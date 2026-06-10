"use client";
/* ============ WTAF — Sources & Prediction Ledger ============ */
import { useState } from "react";
import { useWtaf, useWtafData } from "@/providers/wtaf-provider";
import { Card, EmptyState } from "../primitives";
import { PageHead, PageButton } from "../shared";
import { SignalVolumeCard } from "../command-center/signal-volume-card";
import { SystemCard } from "../command-center/system-card";

const PAGE_SIZE = 25;

export function SourcesPage() {
  const d = useWtafData();
  const { discovering } = useWtaf();
  const sources = d.sources;

  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(sources.length / PAGE_SIZE));
  // Clamp during render so a shrinking list (e.g. after re-discovery) never lands on an empty page.
  const safePage = Math.min(page, pageCount - 1);
  const pageItems = sources.slice(
    safePage * PAGE_SIZE,
    safePage * PAGE_SIZE + PAGE_SIZE,
  );

  return (
    <div>
      <PageHead
        title="Sources & Agent Management"
        sub="data feeds · prediction accuracy ledger"
      />
      <div className="grid12">
        <Card
          title="Data Sources"
          sub={`${sources.filter((s) => s.live).length} live`}
          className="span6"
          loading={discovering && sources.length === 0}
          updating={discovering && sources.length > 0}
          action={<></>}
        >
          {sources.length === 0 ? (
            <EmptyState
              label="No data sources yet"
              sub="Run a discovery to ingest sources"
            />
          ) : (
            <div style={{ display: "flex", flexDirection: "column" }}>
              {pageItems.map((s, i) => (
                <div
                  key={s.name}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    padding: "10px 0",
                    borderBottom:
                      i < pageItems.length - 1
                        ? "1px solid var(--stroke)"
                        : "none",
                  }}
                >
                  <span
                    className="chip"
                    style={{ fontSize: 9, width: 58, justifyContent: "center" }}
                  >
                    {s.kind}
                  </span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 500 }}>
                      {s.name}
                    </div>
                    <div
                      className="mono"
                      style={{ fontSize: 10, color: "var(--t-lo)" }}
                    >
                      {s.freq} · {s.items} items
                    </div>
                  </div>
                </div>
              ))}
              {pageCount > 1 && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 12,
                    marginTop: 14,
                    paddingTop: 12,
                    borderTop: "1px solid var(--stroke)",
                  }}
                >
                  <PageButton
                    label="‹ Prev"
                    disabled={safePage === 0}
                    onClick={() => setPage(safePage - 1)}
                  />
                  <span
                    className="mono"
                    style={{ fontSize: 12, color: "var(--t-mid)" }}
                  >
                    Page {safePage + 1} of {pageCount}
                  </span>
                  <PageButton
                    label="Next ›"
                    disabled={safePage >= pageCount - 1}
                    onClick={() => setPage(safePage + 1)}
                  />
                </div>
              )}
            </div>
          )}
        </Card>

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
          className="span12"
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
                gridTemplateColumns: "1fr 1fr",
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

        {/* System health & monitoring */}
        <div className="span12" style={{ marginTop: 4 }}>
          <div className="label-xs">System Health & Monitoring</div>
        </div>
        <SignalVolumeCard
          signalVolume={d.signalVolume}
          discovering={discovering}
        />
        <SystemCard system={d.system} discovering={discovering} />
      </div>
    </div>
  );
}
