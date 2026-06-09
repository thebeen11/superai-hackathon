"use client";
/* ============ RAIJIN — Command Center (container) ============ */
import { useRaijinData } from "@/providers/raijin-provider";
import type { ShellActions } from "../shared";
import { CouncilCard } from "./council-card";
import { BriefingCard } from "./briefing-card";
import { SentimentCard } from "./sentiment-card";
import { WatchlistCard } from "./watchlist-card";
import { ThesisQuickCard } from "./thesis-quick-card";
import { SignalVolumeCard } from "./signal-volume-card";
import { TrackersCard } from "./trackers-card";
import { SystemCard } from "./system-card";
import { CatalystsCard } from "./catalysts-card";
import { ThemesCard } from "./themes-card";

export function CommandCenter({ actions }: { actions: ShellActions }) {
  const d = useRaijinData();
  const freddy = d.agents.find((a) => a.id === "freddy") ?? d.agents[0];

  return (
    <div className="grid12">
      <CouncilCard agents={d.agents} pipeline={d.pipeline} onOpenAgent={actions.onOpenAgent} />
      <BriefingCard briefing={d.briefing} freddy={freddy} />
      <SentimentCard sentiment={d.sentiment} />
      <WatchlistCard watchlist={d.watchlist} />
      <ThesisQuickCard thesis={d.thesisCountdown} onNav={actions.onNav} onNewTracker={actions.onNewTracker} />
      <SignalVolumeCard signalVolume={d.signalVolume} />
      <TrackersCard trackers={d.trackers} onOpenContext={actions.onOpenContext} onNav={actions.onNav} />
      <SystemCard system={d.system} />
      <CatalystsCard catalysts={d.catalysts} />
      <ThemesCard themes={d.themes} />
    </div>
  );
}
