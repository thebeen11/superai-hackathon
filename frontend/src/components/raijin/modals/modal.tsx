"use client";
import type { ReactNode } from "react";

/** Backdrop + centered glass dialog. Click outside to close. */
export function Modal({ children, onClose, w = 480 }: { children: ReactNode; onClose: () => void; w?: number }) {
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 70, background: "rgba(5,7,12,0.6)", backdropFilter: "blur(4px)", display: "grid", placeItems: "center", padding: 24, animation: "rise .18s" }}>
      <div onClick={(e) => e.stopPropagation()} className="card" style={{ width: w, maxWidth: "94vw", maxHeight: "90vh", overflowY: "auto", animation: "rise .26s" }}>{children}</div>
    </div>
  );
}
