"use client";
/* ============ WTAF — dashboard chrome (persistent shell around routed pages) ============ */
import type { ReactNode } from "react";
import { WtafProvider, useWtaf } from "@/providers/wtaf-provider";
import { ShellUIProvider, ShellModals } from "@/providers/shell-ui-provider";
import { Sidebar } from "./sidebar";
import { TopBar } from "./topbar";
import { LoadingScreen, ErrorScreen } from "./status-screen";

/**
 * Inner shell — runs inside the providers, gates on the snapshot load, then renders
 * the persistent sidebar + topbar around the routed page (`children`). Lives in the
 * root layout so it survives navigation and loads the snapshot once.
 */
function Shell({ children }: { children: ReactNode }) {
  const { data, loading, error, refresh } = useWtaf();

  // Full-screen loader only on the initial load (no data yet). Refresh/discovery
  // keep the dashboard mounted so cards can show per-region loaders instead.
  if (loading && !data) return <LoadingScreen />;
  if (error || !data) return <ErrorScreen message={error?.message ?? "No data"} onRetry={refresh} />;

  return (
    <div className="app-root" style={{ display: "flex", height: "100vh", position: "relative", zIndex: 1 }}>
      <Sidebar />
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <TopBar />
        <main style={{ flex: 1, overflowY: "auto", padding: "18px 20px 28px" }}>{children}</main>
      </div>
      <ShellModals />
    </div>
  );
}

export function DashboardChrome({ children }: { children: ReactNode }) {
  return (
    <WtafProvider>
      <ShellUIProvider>
        <Shell>{children}</Shell>
      </ShellUIProvider>
    </WtafProvider>
  );
}
