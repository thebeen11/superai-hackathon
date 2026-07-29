"use client";
/* ============ WTAF — Sources ============
 *
 * The audit ledger. Every document the council read gets a row, whether or not any
 * agent ended up quoting it — "we read this and nothing turned on it" is a fact the
 * Commander should be able to see, not one to quietly omit.
 */
import { useState } from "react";
import type { SourceDoc } from "@/lib/types";
import { useWtaf, useWtafData } from "@/providers/wtaf-provider";
import { Card, EmptyState } from "../primitives";
import { PageHead, PageButton } from "../shared";

const PAGE_SIZE = 25;

function fmtDate(iso?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleDateString(undefined, { day: "2-digit", month: "short" });
}

function Pager({
  page,
  pageCount,
  onPage,
}: {
  page: number;
  pageCount: number;
  onPage: (n: number) => void;
}) {
  if (pageCount <= 1) return null;
  return (
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
      <PageButton label="‹ Prev" disabled={page === 0} onClick={() => onPage(page - 1)} />
      <span className="mono" style={{ fontSize: 12, color: "var(--t-mid)" }}>
        Page {page + 1} of {pageCount}
      </span>
      <PageButton
        label="Next ›"
        disabled={page >= pageCount - 1}
        onClick={() => onPage(page + 1)}
      />
    </div>
  );
}

function DocRow({ doc, last }: { doc: SourceDoc; last: boolean }) {
  const [open, setOpen] = useState(false);
  const cited = doc.citedBy.length;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 12,
        padding: "10px 0",
        borderBottom: last ? "none" : "1px solid var(--stroke)",
        // Read but never quoted — present, but visibly not load-bearing.
        opacity: cited ? 1 : 0.6,
      }}
    >
      <span
        className="chip"
        style={{ fontSize: 9, width: 58, flexShrink: 0, justifyContent: "center" }}
      >
        {doc.kind}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <a
          href={doc.url}
          target="_blank"
          rel="noreferrer"
          style={{ fontSize: 12.5, fontWeight: 500, color: "var(--t-hi)", lineHeight: 1.4 }}
          title={doc.url}
        >
          {doc.title} ↗
        </a>
        <div className="mono" style={{ fontSize: 10, color: "var(--t-lo)", marginTop: 3 }}>
          {[doc.author || doc.host, fmtDate(doc.publishedAt), doc.stream]
            .filter(Boolean)
            .join(" · ")}
        </div>
        {(doc.themes.length > 0 || doc.tickers.length > 0) && (
          <div
            className="mono"
            style={{ fontSize: 10, color: "var(--t-faint)", marginTop: 3 }}
          >
            {[...doc.tickers, ...doc.themes].join(" · ")}
          </div>
        )}
        {open && cited > 0 && (
          <div
            className="mono"
            style={{ fontSize: 10.5, color: "var(--t-lo)", marginTop: 5 }}
          >
            cited by {doc.citedBy.join(", ")}
          </div>
        )}
      </div>
      {cited > 0 ? (
        <button
          onClick={() => setOpen(!open)}
          className="chip mono"
          style={{
            fontSize: 9.5,
            flexShrink: 0,
            background: "none",
            color: "var(--blue-bright)",
            borderColor: "color-mix(in oklch, var(--blue) 40%, transparent)",
          }}
        >
          cited {cited}× {open ? "▾" : "▸"}
        </button>
      ) : (
        <span
          className="chip mono"
          style={{ fontSize: 9.5, flexShrink: 0, color: "var(--t-faint)" }}
        >
          uncited
        </span>
      )}
    </div>
  );
}

export function SourcesPage() {
  const d = useWtafData();
  const { discovering } = useWtaf();
  const sources = d.sources;
  const docs = d.sourceDocs;

  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(docs.length / PAGE_SIZE));
  // Clamp during render so a shrinking list (e.g. after re-discovery) never lands on an empty page.
  const safePage = Math.min(page, pageCount - 1);
  const pageItems = docs.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);
  const citedCount = docs.filter((doc) => doc.citedBy.length > 0).length;

  return (
    <div>
      <PageHead title="Data Sources" sub="everything the council read · click any row to verify" />
      <div className="grid12">
        <Card
          title="Channels"
          sub={`${sources.length} live`}
          className="span12"
          loading={discovering && sources.length === 0}
          updating={discovering && sources.length > 0}
        >
          {sources.length === 0 ? (
            <EmptyState label="No data sources yet" sub="Run a discovery to ingest sources" />
          ) : (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {sources.map((s) => (
                <span key={s.name} className="chip" style={{ fontSize: 11 }}>
                  {s.name}
                  <span style={{ color: "var(--t-faint)" }}>{s.items}</span>
                </span>
              ))}
            </div>
          )}
        </Card>

        <Card
          title="Documents the council read"
          sub={
            docs.length
              ? `${docs.length} document${docs.length === 1 ? "" : "s"} · ${citedCount} cited`
              : undefined
          }
          className="span12"
          loading={discovering && docs.length === 0}
          updating={discovering && docs.length > 0}
        >
          {docs.length === 0 ? (
            <EmptyState
              label="No documents yet"
              sub="Run a discovery — every article and transcript ingested shows up here"
            />
          ) : (
            <div style={{ display: "flex", flexDirection: "column" }}>
              {pageItems.map((doc, i) => (
                <DocRow key={doc.url} doc={doc} last={i === pageItems.length - 1} />
              ))}
              <Pager page={safePage} pageCount={pageCount} onPage={setPage} />
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
