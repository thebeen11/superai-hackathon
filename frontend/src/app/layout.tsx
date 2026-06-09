import type { Metadata } from "next";
import { Locator } from "@/components/dev/locator";
import "./globals.css";

export const metadata: Metadata = {
  title: "WTAF Fund",
  description: "Hedge Fund AI Agent Council — institutional research terminal.",
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
