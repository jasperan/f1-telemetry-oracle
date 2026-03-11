"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import clsx from "clsx";
import { useStore } from "@/lib/store";

interface ComparisonData {
  distance_points: Array<{
    distance_m: number;
    sim_speed: number;
    real_speed: number;
    sim_throttle: number;
    real_throttle: number;
    sim_brake: number;
    real_brake: number;
    speed_delta: number;
  }>;
  sector_deltas: Array<{
    sector: number;
    sim_time_ms: number;
    real_time_ms: number;
    delta_ms: number;
  }>;
  total_delta_ms: number;
  sim_lap: { lap_id: string; lap_time_ms: number; driver_code: string };
  real_lap: { lap_id: string; lap_time_ms: number; driver_code: string };
}

type Channel = "speed" | "throttle" | "brake";

const CHANNEL_CONFIG: Record<
  Channel,
  { simKey: string; realKey: string; label: string; color: string; max: number; unit: string }
> = {
  speed: {
    simKey: "sim_speed",
    realKey: "real_speed",
    label: "Speed",
    color: "#00D4FF",
    max: 370,
    unit: "KPH",
  },
  throttle: {
    simKey: "sim_throttle",
    realKey: "real_throttle",
    label: "Throttle",
    color: "#00FF87",
    max: 1.0,
    unit: "%",
  },
  brake: {
    simKey: "sim_brake",
    realKey: "real_brake",
    label: "Brake",
    color: "#FF3B3B",
    max: 1.0,
    unit: "%",
  },
};

/** Sector delta chip -- green if faster, red if slower. */
function SectorDelta({
  sector,
  delta_ms,
  sim_ms,
  real_ms,
}: {
  sector: number;
  delta_ms: number;
  sim_ms: number;
  real_ms: number;
}) {
  const faster = delta_ms < 0;
  return (
    <div className="flex flex-col items-center gap-1 flex-1">
      <span className="data-label">S{sector}</span>
      <div
        className={clsx(
          "w-full py-1.5 rounded text-center font-mono text-data-sm",
          faster
            ? "bg-telemetry-delta-negative/20 text-telemetry-delta-negative"
            : delta_ms === 0
              ? "bg-race-border text-race-muted"
              : "bg-telemetry-delta-positive/20 text-telemetry-delta-positive"
        )}
      >
        {faster ? "" : "+"}
        {(delta_ms / 1000).toFixed(3)}
      </div>
      <div className="flex gap-2 text-data-xs text-race-muted font-mono">
        <span className="text-telemetry-speed">
          {(sim_ms / 1000).toFixed(3)}
        </span>
        <span>/</span>
        <span className="text-telemetry-steering">
          {(real_ms / 1000).toFixed(3)}
        </span>
      </div>
    </div>
  );
}

/** Custom tooltip for the comparison chart. */
function ComparisonTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: number;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-race-card border border-race-border rounded px-3 py-2 shadow-lg">
      <div className="text-data-xs text-race-muted font-mono mb-1">
        {Math.round(label ?? 0)}m
      </div>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2">
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: p.color }}
          />
          <span className="text-data-xs text-race-muted">{p.name}:</span>
          <span className="text-data-sm font-mono text-race-text">
            {typeof p.value === "number" ? p.value.toFixed(1) : p.value}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function SimVsReal() {
  const { selectedLapIds } = useStore();
  const [data, setData] = useState<ComparisonData | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeChannel, setActiveChannel] = useState<Channel>("speed");
  const [error, setError] = useState<string | null>(null);

  const fetchComparison = useCallback(async (lapId: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/compare/sim-vs-real?lap=${lapId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: ComparisonData = await res.json();
      setData(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-fetch when a sim lap is selected
  useEffect(() => {
    if (selectedLapIds.length > 0) {
      fetchComparison(selectedLapIds[0]);
    }
  }, [selectedLapIds, fetchComparison]);

  const cfg = CHANNEL_CONFIG[activeChannel];

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-header">
        <span className="panel-title">Sim vs Real</span>
        <div className="flex gap-1">
          {(Object.keys(CHANNEL_CONFIG) as Channel[]).map((ch) => (
            <button
              key={ch}
              onClick={() => setActiveChannel(ch)}
              className={clsx(
                "px-2 py-0.5 rounded text-data-xs font-mono uppercase transition-colors",
                activeChannel === ch
                  ? "bg-race-border text-race-text"
                  : "text-race-muted hover:text-race-text"
              )}
            >
              {ch}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 p-3 flex flex-col gap-3 overflow-hidden">
        {loading && (
          <div className="flex-1 flex items-center justify-center">
            <div className="w-6 h-6 border-2 border-telemetry-speed border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {error && (
          <div className="flex-1 flex items-center justify-center">
            <span className="text-data-sm text-telemetry-brake font-mono">
              {error}
            </span>
          </div>
        )}

        {!loading && !error && !data && (
          <div className="flex-1 flex items-center justify-center text-center">
            <div>
              <span className="text-data-sm text-race-muted">
                Select a sim lap to compare
              </span>
              <p className="text-data-xs text-race-muted mt-1">
                Auto-matches against fastest real lap at same circuit
              </p>
            </div>
          </div>
        )}

        {data && (
          <>
            {/* Lap header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="accent-dot bg-telemetry-speed" />
                <span className="text-data-sm font-mono text-race-text">
                  SIM {data.sim_lap.driver_code}
                </span>
                <span className="text-data-sm font-mono text-telemetry-speed">
                  {(data.sim_lap.lap_time_ms / 1000).toFixed(3)}
                </span>
              </div>
              <div
                className={clsx(
                  "px-2 py-0.5 rounded font-mono text-data-sm",
                  data.total_delta_ms < 0
                    ? "bg-telemetry-delta-negative/20 text-telemetry-delta-negative"
                    : "bg-telemetry-delta-positive/20 text-telemetry-delta-positive"
                )}
              >
                {data.total_delta_ms < 0 ? "" : "+"}
                {(data.total_delta_ms / 1000).toFixed(3)}
              </div>
              <div className="flex items-center gap-2">
                <div className="accent-dot bg-telemetry-steering" />
                <span className="text-data-sm font-mono text-race-text">
                  REAL {data.real_lap.driver_code}
                </span>
                <span className="text-data-sm font-mono text-telemetry-steering">
                  {(data.real_lap.lap_time_ms / 1000).toFixed(3)}
                </span>
              </div>
            </div>

            {/* Overlaid traces */}
            <div className="flex-1 min-h-0">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={data.distance_points}
                  margin={{ top: 5, right: 5, bottom: 5, left: 5 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="#2a2a2a"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="distance_m"
                    tick={{ fill: "#666", fontSize: 10, fontFamily: "JetBrains Mono" }}
                    tickFormatter={(v: number) => `${Math.round(v)}m`}
                    stroke="#2a2a2a"
                  />
                  <YAxis
                    domain={[0, cfg.max]}
                    tick={{ fill: "#666", fontSize: 10, fontFamily: "JetBrains Mono" }}
                    stroke="#2a2a2a"
                    width={40}
                  />
                  <Tooltip content={<ComparisonTooltip />} />
                  <Line
                    type="monotone"
                    dataKey={cfg.simKey}
                    name={`Sim ${cfg.label}`}
                    stroke="#00D4FF"
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey={cfg.realKey}
                    name={`Real ${cfg.label}`}
                    stroke="#FFD700"
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                    strokeDasharray="4 2"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Sector deltas */}
            <div className="flex gap-2">
              {data.sector_deltas.map((s) => (
                <SectorDelta
                  key={s.sector}
                  sector={s.sector}
                  delta_ms={s.delta_ms}
                  sim_ms={s.sim_time_ms}
                  real_ms={s.real_time_ms}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
