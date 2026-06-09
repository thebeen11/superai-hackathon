"use client";
import type { SignalVolume } from "@/lib/types";
import { Card, BarChart } from "../primitives";

export function SignalVolumeCard({ signalVolume }: { signalVolume: SignalVolume }) {
  return (
    <Card title="Signal Volume" sub="this week" className="span3">
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 14 }}>
        <span className="mono display" style={{ fontSize: 26, fontWeight: 700 }}>312</span>
        <span className="mono" style={{ fontSize: 12, color: "var(--t-lo)" }}>transcripts</span>
        <span className="mono" style={{ marginLeft: "auto", fontSize: 12, color: "var(--up)" }}>▲ +18 today</span>
      </div>
      <BarChart bars={signalVolume.bars} height={158} peakLabel={signalVolume.peakLabel} />
    </Card>
  );
}
