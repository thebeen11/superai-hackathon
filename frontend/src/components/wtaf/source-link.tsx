"use client";
/* ============ WTAF — Source citations ============
 *
 * The user-facing half of the no-orphan guardrail (PROJECT_GUIDANCE §12.6): every claim
 * the council makes is either anchored to a document you can open and check, or it says
 * plainly that it isn't. Nothing in between, and nothing silently unattributed.
 */
import { useState } from "react";
import type { Evidence, SourceDoc } from "@/lib/types";

/** Host without the `www.`, or "" when the URL is unparseable. */
export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

const YOUTUBE_HOSTS = new Set(["youtube.com", "m.youtube.com", "youtu.be"]);

/**
 * The link a citation actually opens.
 *
 * For YouTube, appends `?t=Ns` so the video starts at the moment the quote was said —
 * the backend finds that offset by matching the quote against the transcript segments,
 * so this lands on the claim rather than the top of a 40-minute video.
 */
export function sourceHref(url: string, timestampStart?: number): string {
  if (timestampStart == null || timestampStart <= 0) return url;
  try {
    const u = new URL(url);
    if (!YOUTUBE_HOSTS.has(u.hostname.replace(/^www\./, ""))) return url;
    u.searchParams.set("t", `${Math.floor(timestampStart)}s`);
    return u.toString();
  } catch {
    return url;
  }
}

/** Seconds → H:MM:SS (or M:SS under an hour), for the timestamp badge. */
export function fmtOffset(seconds: number): string {
  const s = Math.floor(seconds);
  const mm = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return s >= 3600 ? `${Math.floor(s / 3600)}:${String(mm).padStart(2, "0")}:${ss}` : `${mm}:${ss}`;
}

const linkStyle: React.CSSProperties = {
  display: "block",
  fontSize: 10.5,
  color: "var(--t-faint)",
  marginTop: 4,
  lineHeight: 1.4,
  textDecoration: "none",
};

/** One citation: the quote, who published it, and where it opens. */
export function SourceLink({
  evidence,
  sources,
}: {
  evidence: Evidence;
  sources?: SourceDoc[];
}) {
  const doc = sources?.find((s) => s.url === evidence.sourceUrl);
  const label = doc?.author || doc?.host || hostOf(evidence.sourceUrl) || "source";
  const at = evidence.timestampStart;
  return (
    <a
      href={sourceHref(evidence.sourceUrl, at)}
      target="_blank"
      rel="noreferrer"
      className="mono"
      style={linkStyle}
      title={doc?.title ?? evidence.sourceUrl}
    >
      “{evidence.quote}” ↗
      <span style={{ color: "var(--t-lo)", marginLeft: 6 }}>
        {label}
        {at != null && at > 0 ? ` · ${fmtOffset(at)}` : ""}
      </span>
    </a>
  );
}

/** Shown where an agent produced a claim it could not tie to anything in the corpus. */
export function NoSource({ label = "not source-anchored" }: { label?: string }) {
  return (
    <div
      className="mono"
      style={{ fontSize: 10.5, color: "var(--t-faint)", marginTop: 4, opacity: 0.55 }}
    >
      {label}
    </div>
  );
}

/**
 * A claim's citations. Shows `max` inline and hides the rest behind a toggle — the
 * signposts card used to render only the first and drop everything else on the floor.
 */
export function EvidenceList({
  items,
  sources,
  max = 1,
  emptyLabel,
}: {
  items: Evidence[];
  sources?: SourceDoc[];
  max?: number;
  /** Set to render an explicit "unsourced" marker when there is no evidence at all. */
  emptyLabel?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  if (!items.length) return emptyLabel ? <NoSource label={emptyLabel} /> : null;

  const shown = expanded ? items : items.slice(0, max);
  const hidden = items.length - shown.length;
  return (
    <div>
      {shown.map((e, i) => (
        <SourceLink key={`${e.sourceUrl}-${i}`} evidence={e} sources={sources} />
      ))}
      {(hidden > 0 || expanded) && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mono"
          style={{
            marginTop: 4,
            padding: 0,
            fontSize: 10.5,
            background: "none",
            border: "none",
            color: "var(--blue-bright)",
          }}
        >
          {expanded ? "− fewer" : `+${hidden} more source${hidden > 1 ? "s" : ""}`}
        </button>
      )}
    </div>
  );
}
