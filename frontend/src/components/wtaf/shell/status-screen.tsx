"use client";
/* Full-screen loading / error states for the snapshot fetch. */
export function LoadingScreen() {
  return (
    <div style={{ display: "grid", placeItems: "center", height: "100vh", position: "relative", zIndex: 1 }}>
      <div style={{ textAlign: "center" }}>
        <span style={{ width: 30, height: 30, borderRadius: 99, border: "3px solid var(--blue)", borderTopColor: "transparent", animation: "spin .8s linear infinite", display: "inline-block" }} />
        <div className="mono" style={{ marginTop: 14, fontSize: 12, color: "var(--t-lo)" }}>Loading council snapshot…</div>
      </div>
    </div>
  );
}

export function ErrorScreen({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div style={{ display: "grid", placeItems: "center", height: "100vh", position: "relative", zIndex: 1 }}>
      <div className="card card-pad" style={{ textAlign: "center", maxWidth: 360 }}>
        <div className="display" style={{ fontSize: 16, fontWeight: 600, color: "var(--down)" }}>Connection error</div>
        <div style={{ fontSize: 12.5, color: "var(--t-mid)", marginTop: 8 }}>{message}</div>
        <button onClick={onRetry} className="primary-btn" style={{ marginTop: 16 }}>Retry</button>
      </div>
    </div>
  );
}
