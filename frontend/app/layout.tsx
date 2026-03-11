import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "F1 Telemetry Oracle — Race Engineer AI",
  description:
    "AI-powered F1 race engineer dashboard with live telemetry, sim vs real comparison, and strategy advice. Backed by Oracle 26ai.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen bg-race-bg font-sans text-race-text">
        <header className="h-12 border-b border-race-border flex items-center px-4 bg-race-surface">
          <div className="flex items-center gap-3">
            <div className="w-3 h-3 rounded-full bg-telemetry-speed animate-pulse-fast" />
            <h1 className="font-mono text-data-sm uppercase tracking-widest text-race-text">
              F1 Telemetry Oracle
            </h1>
            <span className="text-data-xs text-race-muted font-mono">
              Race Engineer AI
            </span>
          </div>
          <div className="ml-auto flex items-center gap-4">
            <div id="session-selector" />
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-telemetry-speed" />
              <span className="text-data-xs font-mono text-race-muted">
                CONNECTED
              </span>
            </div>
          </div>
        </header>
        <main className="h-[calc(100vh-3rem)]">{children}</main>
      </body>
    </html>
  );
}
