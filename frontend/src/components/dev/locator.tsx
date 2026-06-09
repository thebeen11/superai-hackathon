"use client";
/**
 * LocatorJS — Alt/Option-click any component in the browser to open its source
 * in your editor. Dev-only: the dynamic import keeps it out of production builds.
 * Docs: https://www.locatorjs.com  (configure your editor with the in-page UI)
 */
import { useEffect } from "react";

export function Locator() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "development") return;
    import("@locator/runtime").then(({ default: setupLocatorUI }) => setupLocatorUI());
  }, []);

  return null;
}
