import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Raijin Terminal",
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
      </body>
    </html>
  );
}
