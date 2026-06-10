"use client";
/**
 * ShellUI — overlay (modal/drawer) state shared across routed pages.
 *
 * Page-to-page navigation is URL-based (App Router), but the agent drawer, debate,
 * context-preview and new-tracker overlays are transient and live here as React state.
 * Pages trigger them with `useShellActions()`; `<ShellModals/>` (mounted once, after the
 * snapshot has loaded) renders the active overlay.
 */
import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { ShellActions } from "@/components/wtaf/shared";
import { useWtaf, useWtafData } from "@/providers/wtaf-provider";
import { AgentDrawer } from "@/components/wtaf/agents";
import { ContextModal } from "@/components/wtaf/modals/context-modal";
import { NewTrackerModal } from "@/components/wtaf/modals/new-tracker-modal";
import { DebateModal } from "@/components/wtaf/modals/debate-modal";

interface ShellUIState {
  agentId: string | null;
  contextTracker: string | null;
  newTracker: boolean;
  debateOpen: boolean;
  actions: ShellActions;
  closeAgent: () => void;
  closeContext: () => void;
  closeNewTracker: () => void;
  closeDebate: () => void;
}

const ShellUIContext = createContext<ShellUIState | null>(null);

export function ShellUIProvider({ children }: { children: ReactNode }) {
  const [agentId, setAgentId] = useState<string | null>(null);
  const [contextTracker, setContextTracker] = useState<string | null>(null);
  const [newTracker, setNewTracker] = useState(false);
  const [debateOpen, setDebateOpen] = useState(false);

  const value = useMemo<ShellUIState>(
    () => ({
      agentId,
      contextTracker,
      newTracker,
      debateOpen,
      actions: {
        onOpenAgent: setAgentId,
        onOpenContext: setContextTracker,
        onNewTracker: () => setNewTracker(true),
        onOpenDebate: () => setDebateOpen(true),
      },
      closeAgent: () => setAgentId(null),
      closeContext: () => setContextTracker(null),
      closeNewTracker: () => setNewTracker(false),
      closeDebate: () => setDebateOpen(false),
    }),
    [agentId, contextTracker, newTracker, debateOpen],
  );

  return <ShellUIContext.Provider value={value}>{children}</ShellUIContext.Provider>;
}

function useShellUI(): ShellUIState {
  const ctx = useContext(ShellUIContext);
  if (!ctx) throw new Error("useShellUI must be used within <ShellUIProvider>");
  return ctx;
}

/** Actions pages/cards call to open an overlay. */
export function useShellActions(): ShellActions {
  return useShellUI().actions;
}

/**
 * Renders the active overlay. Mounted inside the loaded-data gate so the modals
 * (which read `useWtafData()`) always have a snapshot available.
 */
export function ShellModals() {
  const ui = useShellUI();
  const data = useWtafData();
  const { activity, liveStatus } = useWtaf();

  // Agents live in both the legacy flat list and the 5-tier squads.
  const allAgents = [...data.agents, ...data.tiers.flatMap((t) => t.squad)];
  const agent = ui.agentId ? allAgents.find((a) => a.id === ui.agentId) ?? null : null;
  const entries = ui.agentId ? activity.filter((e) => e.agentId === ui.agentId) : [];
  const live = ui.agentId ? liveStatus[ui.agentId] : undefined;

  return (
    <>
      {agent && <AgentDrawer agent={agent} entries={entries} live={live} onClose={ui.closeAgent} />}
      {ui.contextTracker && (
        <ContextModal trackerName={ui.contextTracker} onClose={ui.closeContext} />
      )}
      {ui.newTracker && <NewTrackerModal onClose={ui.closeNewTracker} />}
      {ui.debateOpen && <DebateModal debate={data.debate} onClose={ui.closeDebate} />}
    </>
  );
}
