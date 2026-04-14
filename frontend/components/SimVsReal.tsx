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
    color: "#4cb8d4",
    max: 370,
    unit: "KPH",
  },
  throttle: {
    simKey: "sim_throttle",
    realKey: "real_throttle",
    label: "Throttle",
    color: "#45d48a",
    max: 1.0,
    unit: "%",
  },
  brake: {
    simKey: "sim_brake",
    realKey: "real_brake",
    label: "Brake",
    color: "#e05555",
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
    <div className="flex flex-col items-center gap-1.5 flex-1">
      <span className="data-label">S{sector}</span>
      <div
        className={clsx(
          "w-full py-1.5 rounded-lg text-center font-mono text-data-sm transition-colors duration-300",
          faster
            ? "bg-accent-positive/10 text-accent-positive border border-accent-positive/15"
            : delta_ms === 0
              ? "bg-race-border/30 text-race-muted border border-race-border/30"
              : "bg-accent-negative/10 text-accent-negative border border-accent-negative/15"
        )}
      >
        {faster ? "" : "+"}
        {(delta_ms / 1000).toFixed(3)}
      </div>
      <div className="flex gap-2 text-data-xs text-race-muted/60 font-mono">
        <span className="text-accent-primary">
          {(sim_ms / 1000).toFixed(3)}
        </span>
        <span className="text-race-muted/30">/</span>
        <span className="text-accent-warning">
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
    <div className="bg-race-card/95 border border-race-border/50 rounded-lg px-3 py-2 shadow-panel backdrop-blur-sm">
      <div className="text-data-xs text-race-muted/60 font-mono mb-1.5">
        {Math.round(label ?? 0)}m
      </div>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2 py-0.5">
          <div
            className="w-1.5 h-1.5 rounded-full"
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
    <article className="panel h-full flex flex-col">
      <div className="panel-header">
        <span className="panel-title">Sim vs real</span>
        <div className="flex gap-0.5">
          {(Object.keys(CHANNEL_CONFIG) as Channel[]).map((ch) => (
            <button
              key={ch}
              onClick={() => setActiveChannel(ch)}
              className={clsx(
                "chip-btn",
                activeChannel === ch && "active"
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
            <div className="w-5 h-5 spinner" />
          </div>
        )}

        {error && (
          <div className="flex-1 flex items-center justify-center animate-fade-in">
            <span className="text-data-sm text-accent-negative font-mono">
              {error}
            </span>
          </div>
        )}

        {!loading && !error && !data && (
          <div className="flex-1 flex items-center justify-center text-center animate-fade-in">
            <div>
              <span className="text-data-sm text-race-muted">
                Select a sim lap to compare
              </span>
              <p className="text-data-xs text-race-muted/50 mt-1.5">
                Auto-matches against fastest real lap at same circuit
              </p>
            </div>
          </div>
        )}

        {data && (
          <>
            {/* Lap header */}
            <div className="flex items-center justify-between animate-fade-in">
              <div className="flex items-center gap-2">
                <div className="accent-dot bg-accent-primary" />
                <span className="text-data-sm font-mono text-race-text">
                  Sim {data.sim_lap.driver_code}
                </span>
                <span className="text-data-sm font-mono text-accent-primary">
                  {(data.sim_lap.lap_time_ms / 1000).toFixed(3)}
                </span>
              </div>
              <div
                className={clsx(
                  "px-2.5 py-1 rounded-lg font-mono text-data-sm transition-colors",
                  data.total_delta_ms < 0
                    ? "bg-accent-positive/10 text-accent-positive border border-accent-positive/15"
                    : "bg-accent-negative/10 text-accent-negative border border-accent-negative/15"
                )}
              >
                {data.total_delta_ms < 0 ? "" : "+"}
                {(data.total_delta_ms / 1000).toFixed(3)}
              </div>
              <div className="flex items-center gap-2">
                <div className="accent-dot bg-accent-warning" />
                <span className="text-data-sm font-mono text-race-text">
                  Real {data.real_lap.driver_code}
                </span>
                <span className="text-data-sm font-mono text-accent-warning">
                  {(data.real_lap.lap_time_ms / 1000).toFixed(3)}
                </span>
              </div>
            </div>

            {/* Overlaid traces */}
            <div className="flex-1 min-h-0 rounded-lg overflow-hidden bg-race-surface/20">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={data.distance_points}
                  margin={{ top: 8, right: 8, bottom: 5, left: 5 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="rgba(38, 38, 46, 0.5)"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="distance_m"
                    tick={{ fill: "#6b6b78", fontSize: 10, fontFamily: "JetBrains Mono" }}
                    tickFormatter={(v: number) => `${Math.round(v)}m`}
                    stroke="rgba(38, 38, 46, 0.4)"
                  />
                  <YAxis
                    domain={[0, cfg.max]}
                    tick={{ fill: "#6b6b78", fontSize: 10, fontFamily: "JetBrains Mono" }}
                    stroke="rgba(38, 38, 46, 0.4)"
                    width={40}
                  />
                  <Tooltip content={<ComparisonTooltip />} />
                  <Line
                    type="monotone"
                    dataKey={cfg.simKey}
                    name={`Sim ${cfg.label}`}
                    stroke="#4cb8d4"
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey={cfg.realKey}
                    name={`Real ${cfg.label}`}
                    stroke="#d4a845"
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
    </article>
  );
}
