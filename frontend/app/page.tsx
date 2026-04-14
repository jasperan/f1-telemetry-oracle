"use client";

import dynamic from "next/dynamic";

// Dynamic imports to avoid SSR issues with WebSocket/Three.js/Recharts
const LiveTelemetry = dynamic(() => import("@/components/LiveTelemetry"), {
  ssr: false,
  loading: () => <PanelSkeleton label="Live telemetry" index={0} />,
});
const SimVsReal = dynamic(() => import("@/components/SimVsReal"), {
  ssr: false,
  loading: () => <PanelSkeleton label="Sim vs real" index={3} />,
});
const TrackMap3D = dynamic(() => import("@/components/TrackMap3D"), {
  ssr: false,
  loading: () => <PanelSkeleton label="3D track map" index={1} />,
});
const StrategyAdvisor = dynamic(() => import("@/components/StrategyAdvisor"), {
  ssr: false,
  loading: () => <PanelSkeleton label="Strategy advisor" index={4} />,
});
const RaceEngineerChat = dynamic(
  () => import("@/components/RaceEngineerChat"),
  {
    ssr: false,
    loading: () => <PanelSkeleton label="Race engineer" index={2} />,
  }
);
const HistoricalExplorer = dynamic(
  () => import("@/components/HistoricalExplorer"),
  {
    ssr: false,
    loading: () => <PanelSkeleton label="Historical" index={5} />,
  }
);

function PanelSkeleton({ label, index = 0 }: { label: string; index?: number }) {
  return (
    <div
      className="panel h-full flex items-center justify-center animate-fade-in"
      style={{ animationDelay: `${index * 80}ms`, animationFillMode: "backwards" }}
    >
      <div className="text-center">
        <div className="w-5 h-5 spinner mx-auto mb-3" />
        <span className="panel-title">{label}</span>
      </div>
    </div>
  );
}

export default function Dashboard() {
  return (
    <div className="h-full grid grid-cols-1 md:grid-cols-3 grid-rows-6 md:grid-rows-2 gap-1.5 p-1.5 bg-race-bg">
      {/* Row 1: Live Telemetry | 3D Track Map | AI Race Engineer Chat */}
      <section className="min-h-0 animate-fade-in-up stagger-1" style={{ animationFillMode: "backwards" }}>
        <LiveTelemetry />
      </section>
      <section className="min-h-0 animate-fade-in-up stagger-2" style={{ animationFillMode: "backwards" }}>
        <TrackMap3D />
      </section>
      <section className="min-h-0 animate-fade-in-up stagger-3" style={{ animationFillMode: "backwards" }}>
        <RaceEngineerChat />
      </section>

      {/* Row 2: Sim vs Real | Strategy Advisor | Historical Explorer */}
      <section className="min-h-0 animate-fade-in-up stagger-4" style={{ animationFillMode: "backwards" }}>
        <SimVsReal />
      </section>
      <section className="min-h-0 animate-fade-in-up stagger-5" style={{ animationFillMode: "backwards" }}>
        <StrategyAdvisor />
      </section>
      <section className="min-h-0 animate-fade-in-up stagger-6" style={{ animationFillMode: "backwards" }}>
        <HistoricalExplorer />
      </section>
    </div>
  );
}
