import type { Metadata } from "next";
import { Locator } from "@/components/dev/locator";
import { DashboardChrome } from "@/components/wtaf/shell/dashboard-chrome";
import "./globals.css";

export const metadata: Metadata = {
  title: "WTAF Fund",
  description: "Hedge Fund AI Agent Council — institutional research terminal.",
  icons: {
    icon: [
      { url: "/favicon/favicon.ico", sizes: "any" },
      { url: "/favicon/favicon-32x32.png", type: "image/png", sizes: "32x32" },
      { url: "/favicon/favicon-16x16.png", type: "image/png", sizes: "16x16" },
    ],
    apple: "/favicon/apple-touch-icon.png",
  },
  manifest: "/favicon/site.webmanifest",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // suppressHydrationWarning: browser extensions (Grammarly, Bitdefender, …)
    // mutate <html>/<body> before React hydrates; this silences that benign noise.
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <div className="bg-field" />
        <div className="bg-grid" />
        <DashboardChrome>{children}</DashboardChrome>
        <Locator />
      </body>
    </html>
  );
}
