"use client";
import type { SignalVolume } from "@/lib/types";
import { Card, BarChart, EmptyState } from "../primitives";

export function SignalVolumeCard({ signalVolume, discovering = false }: { signalVolume: SignalVolume; discovering?: boolean }) {
  const isEmpty = signalVolume.bars.length === 0;
  return (
    <Card title="Signal Volume" sub="this week" className="span3"
      loading={discovering && isEmpty} updating={discovering && !isEmpty}>
      {signalVolume.bars.length === 0 ? (
        <EmptyState label="No signal volume yet" sub="run a discovery" minHeight={158} />
      ) : (
        <>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 14 }}>
            <span className="mono" style={{ fontSize: 12, color: "var(--t-lo)" }}>{signalVolume.sub}</span>
            {signalVolume.peakLabel && <span className="mono" style={{ marginLeft: "auto", fontSize: 12, color: "var(--up)" }}>▲ {signalVolume.peakLabel}</span>}
          </div>
          <BarChart bars={signalVolume.bars} height={158} peakLabel={signalVolume.peakLabel} />
        </>
      )}
    </Card>
  );
}
