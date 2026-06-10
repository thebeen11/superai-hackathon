"use client";
import type { SystemStatus } from "@/lib/types";
import { Card, Ring, MiniBar } from "../primitives";

export function SystemCard({ system, discovering = false }: { system: SystemStatus; discovering?: boolean }) {
  const isEmpty = system.bars.length === 0;
  return (
    <Card title="System Status" sub="data pipeline" className="span3"
      loading={discovering && isEmpty} updating={discovering && !isEmpty}>
      <div style={{ display: "flex", gap: 14, alignItems: "center", marginBottom: 13 }}>
        <Ring value={system.coverage} size={92} stroke={8} from="blue" to="blue">
          <div>
            <div className="mono display" style={{ fontSize: 19, fontWeight: 700 }}>{Math.round(system.coverage * 100)}%</div>
            <div className="label-xs" style={{ fontSize: 7.5, color: "var(--blue-bright)" }}>coverage</div>
          </div>
        </Ring>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 11 }}>
          {system.bars.map((b, i) => (
            <div key={i}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                <span style={{ fontSize: 10.5, color: "var(--t-mid)" }}>{b.k}</span>
                <span className="mono" style={{ fontSize: 10.5, color: "var(--t-lo)" }}>{b.txt}</span>
              </div>
              <MiniBar v={b.v} h={4} />
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
