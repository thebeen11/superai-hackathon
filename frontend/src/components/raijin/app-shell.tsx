"use client";
/* ============ RAIJIN — app shell (root) ============ */
import { useMemo, useState } from "react";
import { RaijinProvider, useRaijin } from "@/providers/raijin-provider";
import type { PageId, ShellActions } from "./shared";
import { AgentDrawer } from "./agents";
import { CommandCenter } from "./command-center";
import { SignalTerminal } from "./pages/signal-terminal";
import { BacktestSandbox } from "./pages/backtest-sandbox";
import { SourcesPage } from "./pages/sources-page";
import { IndicatorsPage } from "./pages/indicators-page";
import { Sidebar } from "./shell/sidebar";
import { TopBar } from "./shell/topbar";
import { LoadingScreen, ErrorScreen } from "./shell/status-screen";
import { ContextModal } from "./modals/context-modal";
import { NewTrackerModal } from "./modals/new-tracker-modal";

/** Inner shell — runs inside the provider, so it can read the snapshot. */
function Shell() {
  const { data, loading, error, refresh } = useRaijin();

  const [page, setPage] = useState<PageId>("command");
  const [agentId, setAgentId] = useState<string | null>(null);
  const [contextTracker, setContextTracker] = useState<string | null>(null);
  const [newTracker, setNewTracker] = useState(false);
  const [presetTheme, setPresetTheme] = useState<string | null>(null);

  const actions: ShellActions = useMemo(
    () => ({
      onNav: setPage,
      onOpenAgent: setAgentId,
      onOpenContext: setContextTracker,
      onNewTracker: () => setNewTracker(true),
      onRunBacktest: (themeName?: string) => {
        setPresetTheme(themeName ?? null);
        setPage("backtest");
      },
    }),
    [],
  );

  if (loading) return <LoadingScreen />;
  if (error || !data) return <ErrorScreen message={error?.message ?? "No data"} onRetry={refresh} />;

  const agent = agentId ? data.agents.find((a) => a.id === agentId) ?? null : null;

  return (
    <div className="app-root" style={{ display: "flex", height: "100vh", position: "relative", zIndex: 1 }}>
      <Sidebar page={page} setPage={setPage} />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <TopBar />
        <main style={{ flex: 1, overflowY: "auto", padding: "18px 20px 28px" }}>
          {page === "command" && <CommandCenter actions={actions} />}
          {page === "signals" && <SignalTerminal onOpenContext={setContextTracker} onNewTracker={() => setNewTracker(true)} />}
          {page === "backtest" && <BacktestSandbox presetTheme={presetTheme} />}
          {page === "sources" && <SourcesPage />}
          {page === "indicators" && <IndicatorsPage />}
        </main>
      </div>
      {agent && <AgentDrawer agent={agent} onClose={() => setAgentId(null)} />}
      {contextTracker && <ContextModal trackerName={contextTracker} onClose={() => setContextTracker(null)} />}
      {newTracker && <NewTrackerModal onClose={() => setNewTracker(false)} />}
    </div>
  );
}

export function RaijinApp() {
  return (
    <RaijinProvider>
      <Shell />
    </RaijinProvider>
  );
}
