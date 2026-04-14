import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "F1 Telemetry Oracle -- Race Engineer AI",
  description:
    "AI-powered F1 race engineer dashboard with live telemetry, sim vs real comparison, and strategy advice. Backed by Oracle 23ai.",
  icons: {
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🏎</text></svg>",
  },
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
          href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
        <meta property="og:title" content="F1 Telemetry Oracle" />
        <meta property="og:description" content="AI-powered F1 race engineer dashboard backed by Oracle 23ai" />
      </head>
      <body className="min-h-screen bg-race-bg font-sans text-race-text">
        {/* Noise overlay for texture */}
        <div className="noise-overlay" aria-hidden="true" />

        <a href="#main-content" className="skip-to-content">
          Skip to content
        </a>

        <header className="header-bar h-14 border-b border-race-border/50 flex items-center px-5 bg-race-surface/80 backdrop-blur-xl sticky top-0 z-50">
          <nav className="flex items-center gap-4 w-full" aria-label="Primary">
            <div className="flex items-center gap-3">
              <div className="relative">
                <div className="w-2.5 h-2.5 rounded-full bg-accent-primary animate-pulse-fast" />
                <div className="absolute inset-0 w-2.5 h-2.5 rounded-full bg-accent-primary/40 animate-ping" />
              </div>
              <h1 className="font-sans text-[0.9rem] font-semibold tracking-tight text-race-text">
                F1 Telemetry Oracle
              </h1>
              <span className="text-data-xs text-race-muted/60 font-mono font-medium tracking-wide">
                Race Engineer AI
              </span>
            </div>
            <div className="ml-auto flex items-center gap-5">
              <div id="session-selector" />
              <div className="flex items-center gap-2 status-pill">
                <div className="w-1.5 h-1.5 rounded-full bg-accent-positive" />
                <span className="text-[0.65rem] font-mono text-race-muted tracking-wider font-medium">
                  CONNECTED
                </span>
              </div>
            </div>
          </nav>
        </header>
        <main id="main-content" className="h-[calc(100dvh-3.5rem)]">{children}</main>
      </body>
    </html>
  );
}
