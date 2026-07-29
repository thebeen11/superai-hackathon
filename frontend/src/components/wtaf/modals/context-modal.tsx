"use client";
/* Context Preview — fetched per-tracker from the API (own loading state). */
import { useEffect, useState } from "react";
import type { ContextPreview } from "@/lib/types";
import { getContextPreview } from "@/lib/api/wtaf";
import { useWtafData } from "@/providers/wtaf-provider";
import { Dot } from "../primitives";
import { sourceHref } from "../source-link";
import { Modal } from "./modal";

export function ContextModal({ trackerName, onClose }: { trackerName: string; onClose: () => void }) {
  const [c, setC] = useState<ContextPreview | null>(null);
  // The live backend (Layers 1–2) has no per-tracker context endpoint; fall back
  // to the snapshot-derived preview so a 404 doesn't become an unhandled rejection.
  const fallback = useWtafData().contextPreview;

  useEffect(() => {
    let active = true;
    getContextPreview(trackerName)
      .then((res) => { if (active) setC(res); })
      .catch(() => { if (active) setC({ ...fallback, tracker: trackerName }); });
    return () => { active = false; };
  }, [trackerName, fallback]);

  return (
    <Modal onClose={onClose} w={520}>
      <div className="card-pad">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
          <div>
            <div className="label-xs" style={{ marginBottom: 5 }}>Context Preview</div>
            <h3 className="display" style={{ fontSize: 17, fontWeight: 600 }}>{trackerName}</h3>
          </div>
          <button onClick={onClose} style={{ background: "var(--panel-2)", border: "1px solid var(--stroke)", borderRadius: 8, width: 28, height: 28, color: "var(--t-mid)" }}>×</button>
        </div>

        {!c ? (
          <div style={{ height: 180, display: "grid", placeItems: "center" }}>
            <span style={{ width: 22, height: 22, borderRadius: 99, border: "2.5px solid var(--blue)", borderTopColor: "transparent", animation: "spin .8s linear infinite" }} />
          </div>
        ) : (
          <>
            <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
              <span className="chip"><Dot tone="blue" pulse={false} />{c.channel}</span>
              <span className="chip">{c.date}</span>
              <span className="chip" style={{ color: "var(--up)", borderColor: "color-mix(in oklch, var(--up) 40%, transparent)" }}>relevance {(c.score ?? 0).toFixed(2)}</span>
            </div>
            <div style={{ padding: "16px 18px", borderRadius: 12, background: "var(--inset)", borderLeft: "2px solid var(--blue-bright)", marginBottom: 6 }}>
              <p style={{ fontSize: 14.5, lineHeight: 1.55, color: "var(--t-hi)", fontStyle: "italic", textWrap: "pretty" }}>{c.quote}</p>
              <div className="mono" style={{ fontSize: 11, color: "var(--t-lo)", marginTop: 10 }}>{c.speaker}</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 16 }}>
              <div className="mono" style={{ fontSize: 12, color: "var(--t-mid)" }}>timestamp <span style={{ color: "var(--blue-bright)" }}>{c.timestamp}</span></div>
              {c.sourceUrl ? (
                <a
                  href={sourceHref(c.sourceUrl, c.timestampStart)}
                  target="_blank"
                  rel="noreferrer"
                  className="primary-btn"
                  style={{ display: "flex", alignItems: "center", gap: 8 }}
                >
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
                  Go to Source · {c.timestamp}
                </a>
              ) : (
                <span className="mono" style={{ fontSize: 11, color: "var(--t-faint)" }}>
                  no source link
                </span>
              )}
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
