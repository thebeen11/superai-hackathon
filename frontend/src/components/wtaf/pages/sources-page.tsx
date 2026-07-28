"use client";
/* ============ WTAF — Sources ============ */
import { useState } from "react";
import { useWtaf, useWtafData } from "@/providers/wtaf-provider";
import { Card, EmptyState } from "../primitives";
import { PageHead, PageButton } from "../shared";

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
        title="Data Sources"
        sub="data feed management"
      />
      <div className="grid12">
        <Card
          title="Data Sources"
          sub={`${sources.filter((s) => s.live).length} live`}
          className="span12"
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
      </div>
    </div>
  );
}
