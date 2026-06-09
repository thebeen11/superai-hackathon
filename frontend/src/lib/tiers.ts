/**
 * 5-tier agent-council topology — the *structure* of the system (tiers, squads,
 * roles, tools), independent of any live run. This is real architecture, not mock
 * telemetry: Tiers 1–2 (Discovery, Data-Engineering/Routing) are built; Tiers 3–5
 * (Andie analysts, Freddy debate, Winston chairman) are not yet, so their live
 * status is shown as "awaiting build" with neutral metrics.
 *
 * Derived from the mock tiers' skeleton to avoid duplicating ~150 lines, with all
 * invented live metrics (statusText/queue/throughput/log) neutralized.
 */
import type { Tier } from "./types";
import { wtafMock } from "./mock-data";

export const tierTopology: Tier[] = wtafMock.tiers.map((t) => {
  const built = t.n <= 2;
  return {
    ...t,
    status: built ? "active" : "idle",
    statusText: built ? "online" : "awaiting build",
    squad: t.squad.map((a) => ({
      ...a,
      status: built ? "active" : "idle",
      statusText: built ? "online" : "pending",
      queue: 0,
      throughput: "—",
      log: [],
    })),
  };
});
