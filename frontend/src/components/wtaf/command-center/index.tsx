"use client";
/* ============ WTAF — Command Center (container) ============ */
import { useWtaf, useWtafData } from "@/providers/wtaf-provider";
import { useShellActions } from "@/providers/shell-ui-provider";
import { CouncilCard } from "./council-card";
import { ActivityLogCard } from "./activity-log-card";
import { BriefingCard } from "./briefing-card";
import { SentimentCard } from "./sentiment-card";
import { TrackersCard } from "./trackers-card";
import { CatalystsCard } from "./catalysts-card";
import { DebateCard } from "./debate-card";
import { ThemesCard } from "./themes-card";

export function CommandCenter() {
  const d = useWtafData();
  const { discovering } = useWtaf();
  const actions = useShellActions();
  const chairman =
    d.tiers.find((t) => t.key === "chairman")?.squad[0] ?? d.agents[0];

  return (
    <div className="grid12">
      {/* Winston's headline outputs lead the page — the weekly themes + the 60-sec read,
          side by side. ThemesCard fetches its own runs (weekly, browsable by date). */}
      <ThemesCard onOpenDebate={actions.onOpenDebate} />
      <BriefingCard briefing={d.briefing} chairman={chairman} />
      <CatalystsCard catalysts={d.catalysts} />
      <DebateCard
        debate={d.debate}
        tiers={d.tiers}
        onOpenDebate={actions.onOpenDebate}
      />

      {/* Council & analysis — sentiment & trackers are backend-backed */}
      <CouncilCard tiers={d.tiers} onOpenAgent={actions.onOpenAgent} />
      <ActivityLogCard />
      <SentimentCard sentiment={d.sentiment} discovering={discovering} />
      <TrackersCard
        trackers={d.trackers}
        onOpenContext={actions.onOpenContext}
        discovering={discovering}
      />
    </div>
  );
}
