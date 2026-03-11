"use client";

import dynamic from "next/dynamic";

// Dynamic imports to avoid SSR issues with WebSocket/Three.js/Recharts
const LiveTelemetry = dynamic(() => import("@/components/LiveTelemetry"), {
  ssr: false,
  loading: () => <PanelSkeleton label="LIVE TELEMETRY" />,
});
const SimVsReal = dynamic(() => import("@/components/SimVsReal"), {
  ssr: false,
  loading: () => <PanelSkeleton label="SIM VS REAL" />,
});
const TrackMap3D = dynamic(() => import("@/components/TrackMap3D"), {
  ssr: false,
  loading: () => <PanelSkeleton label="3D TRACK MAP" />,
});
const StrategyAdvisor = dynamic(() => import("@/components/StrategyAdvisor"), {
  ssr: false,
  loading: () => <PanelSkeleton label="STRATEGY ADVISOR" />,
});
const RaceEngineerChat = dynamic(
  () => import("@/components/RaceEngineerChat"),
  {
    ssr: false,
    loading: () => <PanelSkeleton label="RACE ENGINEER" />,
  }
);
const HistoricalExplorer = dynamic(
  () => import("@/components/HistoricalExplorer"),
  {
    ssr: false,
    loading: () => <PanelSkeleton label="HISTORICAL" />,
  }
);

function PanelSkeleton({ label }: { label: string }) {
  return (
    <div className="panel h-full flex items-center justify-center">
      <div className="text-center">
        <div className="w-6 h-6 border-2 border-telemetry-speed border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        <span className="panel-title">{label}</span>
      </div>
    </div>
  );
}

export default function Dashboard() {
  return (
    <div className="h-full grid grid-cols-1 md:grid-cols-3 grid-rows-6 md:grid-rows-2 gap-px bg-race-border">
      {/* Row 1: Live Telemetry | 3D Track Map | AI Race Engineer Chat */}
      <div className="bg-race-bg">
        <LiveTelemetry />
      </div>
      <div className="bg-race-bg">
        <TrackMap3D />
      </div>
      <div className="bg-race-bg">
        <RaceEngineerChat />
      </div>

      {/* Row 2: Sim vs Real | Strategy Advisor | Historical Explorer */}
      <div className="bg-race-bg">
        <SimVsReal />
      </div>
      <div className="bg-race-bg">
        <StrategyAdvisor />
      </div>
      <div className="bg-race-bg">
        <HistoricalExplorer />
      </div>
    </div>
  );
}
