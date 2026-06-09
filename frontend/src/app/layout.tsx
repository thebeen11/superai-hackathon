import type { Metadata } from "next";
import { Locator } from "@/components/dev/locator";
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
    <html lang="en">
      <body>
        <div className="bg-field" />
        <div className="bg-grid" />
        {children}
        <Locator />
      </body>
    </html>
  );
}
