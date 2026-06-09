"use client";
/* ============ WTAF — Command Center (container) ============ */
import { useWtafData } from "@/providers/wtaf-provider";
import type { ShellActions } from "../shared";
import { CouncilCard } from "./council-card";
import { BriefingCard } from "./briefing-card";
import { SentimentCard } from "./sentiment-card";
import { TrackersCard } from "./trackers-card";
import { CatalystsCard } from "./catalysts-card";
import { DebateCard } from "./debate-card";
import { ThemesCard } from "./themes-card";

export function CommandCenter({ actions }: { actions: ShellActions }) {
  const d = useWtafData();
  const chairman = d.tiers.find((t) => t.key === "chairman")?.squad[0] ?? d.agents[0];

  return (
    <div className="grid12">
      {/* Promoted to top */}
      <ThemesCard themes={d.themes} onOpenDebate={actions.onOpenDebate} />
      <CatalystsCard catalysts={d.catalysts} />
      <DebateCard debate={d.debate} tiers={d.tiers} onOpenDebate={actions.onOpenDebate} />

      {/* Council & analysis */}
      <CouncilCard tiers={d.tiers} onOpenAgent={actions.onOpenAgent} />
      <BriefingCard briefing={d.briefing} chairman={chairman} />
      <SentimentCard sentiment={d.sentiment} />
      <TrackersCard trackers={d.trackers} onOpenContext={actions.onOpenContext} onNav={actions.onNav} />
    </div>
  );
}
