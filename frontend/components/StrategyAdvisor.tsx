"use client";

import { useCallback, useEffect, useState } from "react";
import clsx from "clsx";
import { useStore, TirePrediction } from "@/lib/store";
import { fetchPitWindow, fetchStrategySim, fetchTireLife } from "@/lib/api";

/** Tire compound color lookup. */
const COMPOUND_COLORS: Record<string, string> = {
  SOFT: "#e05555",
  MEDIUM: "#d4a845",
  HARD: "#e8e8ed",
  INTERMEDIATE: "#45d48a",
  WET: "#4ca8e0",
};

/** Tire life gauge -- circular with grip indicator. */
function TireLifeGauge({
  prediction,
  compound,
}: {
  prediction: TirePrediction;
  compound: string;
}) {
  const compoundColor = COMPOUND_COLORS[compound.toUpperCase()] ?? "#666";
  const gripPct = prediction.grip_percent;
  const circumference = 2 * Math.PI * 45;
  const gripOffset = circumference * (1 - gripPct / 100);
  const cliffPct = prediction.cliff_risk * 100;

  return (
    <div className="flex flex-col items-center gap-2.5 animate-fade-in">
      <div className="relative w-32 h-32">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          {/* Background ring */}
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke="var(--color-border)"
            strokeWidth="7"
            opacity="0.4"
          />
          {/* Grip level */}
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke={gripPct > 30 ? compoundColor : "#e05555"}
            strokeWidth="7"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={gripOffset}
            className="transition-all duration-500"
            style={{ filter: `drop-shadow(0 0 4px ${gripPct > 30 ? compoundColor : '#e05555'}40)` }}
          />
          {/* Cliff risk indicator (inner ring) */}
          {cliffPct > 0 && (
            <circle
              cx="50"
              cy="50"
              r="36"
              fill="none"
              stroke="#e05555"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeDasharray={2 * Math.PI * 36}
              strokeDashoffset={2 * Math.PI * 36 * (1 - cliffPct / 100)}
              opacity={0.5}
            />
          )}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono font-semibold text-data-2xl text-race-text">
            {Math.round(gripPct)}
          </span>
          <span className="text-data-xs text-race-muted/60 font-mono">Grip %</span>
        </div>
      </div>

      {/* Compound label */}
      <div className="flex items-center gap-2">
        <div
          className="w-3 h-3 rounded-full"
          style={{ backgroundColor: compoundColor, boxShadow: `0 0 6px ${compoundColor}40` }}
        />
        <span className="font-mono text-data-sm text-race-text uppercase font-medium">
          {compound}
        </span>
      </div>

      {/* Laps remaining */}
      <div className="text-center">
        <span className="font-mono text-data-xl text-race-text font-semibold">
          {prediction.laps_remaining}
        </span>
        <span className="text-data-xs text-race-muted/60 ml-1.5">laps left</span>
      </div>

      {/* Cliff risk bar */}
      {cliffPct > 0 && (
        <div className="w-full max-w-[160px]">
          <div className="flex justify-between mb-1.5">
            <span className="data-label">Cliff risk</span>
            <span
              className={clsx(
                "font-mono text-data-xs",
                cliffPct > 70
                  ? "text-accent-negative"
                  : cliffPct > 40
                    ? "text-accent-warning"
                    : "text-race-muted/60"
              )}
            >
              {Math.round(cliffPct)}%
            </span>
          </div>
          <div className="h-1.5 bg-race-border/30 rounded-full overflow-hidden">
            <div
              className={clsx(
                "h-full rounded-full transition-all duration-500",
                cliffPct > 70
                  ? "bg-accent-negative"
                  : cliffPct > 40
                    ? "bg-accent-warning"
                    : "bg-race-muted/40"
              )}
              style={{ width: `${cliffPct}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

/** Pit window recommendation banner. */
function PitWindowBanner({
  optimalLap,
  compound,
  modelUsed,
}: {
  optimalLap: number;
  compound: string;
  modelUsed?: string;
}) {
  const compoundColor = COMPOUND_COLORS[compound.toUpperCase()] ?? "#666";
  return (
    <div className="bg-accent-primary/8 border border-accent-primary/20 rounded-xl px-3.5 py-2.5 flex items-center gap-3 animate-fade-in">
      <div className="w-8 h-8 rounded-lg border border-accent-primary/40 flex items-center justify-center bg-accent-primary/10">
        <span className="font-mono text-data-sm text-accent-primary font-bold">
          P
        </span>
      </div>
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="text-data-xs text-race-muted/60 font-medium">Recommended pit</span>
          {modelUsed && (
            <span className="text-[0.55rem] font-mono px-1 py-0.5 rounded bg-accent-primary/10 text-accent-primary border border-accent-primary/15 uppercase tracking-wider">
              {modelUsed === "onnx" ? "in-DB ONNX" : "heuristic"}
            </span>
          )}
        </div>
        <div className="font-mono text-data-lg text-race-text font-semibold">
          Lap {optimalLap}
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        <div
          className="w-3 h-3 rounded-full"
          style={{ backgroundColor: compoundColor }}
        />
        <span className="font-mono text-data-sm text-race-text uppercase">
          {compound}
        </span>
      </div>
    </div>
  );
}

/** Ranked strategy row from the Monte Carlo simulator. */
function SimStrategyRow({
  strategy,
  rank,
  winProbability,
  medianTime,
}: {
  strategy: string[];
  rank: number;
  winProbability: number;
  medianTime: number;
}) {
  return (
    <div
      className={clsx(
        "flex items-center gap-2.5 rounded-lg px-2.5 py-2 border",
        rank === 1
          ? "border-accent-primary/30 bg-accent-primary/5"
          : "border-race-border/30 bg-race-surface/50"
      )}
    >
      <span
        className={clsx(
          "w-6 h-6 rounded-md flex items-center justify-center font-mono text-data-xs font-bold flex-shrink-0",
          rank === 1
            ? "bg-accent-primary text-race-bg"
            : "bg-race-border/40 text-race-muted"
        )}
      >
        {rank}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          {strategy.map((compound, i) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 && <span className="text-race-muted/40">→</span>}
              <span
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: COMPOUND_COLORS[compound] ?? "#666" }}
              />
              <span className="font-mono text-data-xs text-race-text uppercase">
                {compound.charAt(0)}
              </span>
            </span>
          ))}
        </div>
        <span className="text-data-xs text-race-muted/50 font-mono">
          median {medianTime.toFixed(1)}s
        </span>
      </div>
      <span
        className={clsx(
          "font-mono text-data-sm font-semibold",
          winProbability > 0.5 ? "text-accent-positive" : "text-race-muted"
        )}
      >
        {(winProbability * 100).toFixed(0)}%
      </span>
    </div>
  );
}

export default function StrategyAdvisor() {
  const { selectedLapIds } = useStore();
  const [loading, setLoading] = useState(false);
  const [simLoading, setSimLoading] = useState(false);
  const [currentCompound, setCurrentCompound] = useState("SOFT");
  const [tirePrediction, setTirePrediction] = useState<TirePrediction | null>(null);
  const [pitWindow, setPitWindow] = useState<{
    optimal_pit_lap: number;
    recommended_compound: string;
    model_used?: string;
    strategy_description?: string;
  } | null>(null);
  const [simResult, setSimResult] = useState<{
    strategies: Array<{
      strategy: string[];
      median_race_time_s: number;
      win_probability: number;
      rank: number;
    }>;
    n_sims: number;
  } | null>(null);

  const fetchPredictions = useCallback(async () => {
    setLoading(true);
    try {
      const tireData = await fetchTireLife({
        tire_compound: currentCompound,
        tire_age_laps: 12,
        track_temp_c: 35.0,
        fuel_load_kg: 80.0,
      });
      setTirePrediction({
        grip_percent: Number(tireData.current_grip_pct ?? 0),
        laps_remaining: Number(tireData.predicted_remaining_laps ?? 0),
        cliff_risk: Math.max(
          0,
          Math.min(1, (50 - Number(tireData.current_grip_pct ?? 0)) / 50)
        ),
        model_name: String(tireData.model_used ?? "heuristic"),
      });

      const pitData = await fetchPitWindow({
        current_lap: 18,
        total_laps: 53,
        tire_compound: currentCompound,
        tire_age_laps: 12,
        position: 5,
        gap_ahead_ms: 1500,
        gap_behind_ms: 8000,
      });
      setPitWindow({
        optimal_pit_lap: Number(pitData.optimal_pit_lap ?? 0),
        recommended_compound: String(pitData.recommended_compound ?? "MEDIUM"),
        model_used: String(pitData.model_used ?? "heuristic"),
        strategy_description: String(pitData.strategy_description ?? ""),
      });
    } catch {
      // Fallback display data if the backend is unreachable
      setTirePrediction({
        grip_percent: 72.5,
        laps_remaining: 8,
        cliff_risk: 0.25,
        model_name: "unavailable",
      });
      setPitWindow({
        optimal_pit_lap: 22,
        recommended_compound: "HARD",
        model_used: "unavailable",
      });
    } finally {
      setLoading(false);
    }
  }, [currentCompound]);

  const runSimulation = useCallback(async () => {
    setSimLoading(true);
    try {
      const result = await fetchStrategySim({
        total_laps: 53,
        track_temp_c: 35.0,
        fuel_start_kg: 110.0,
        n_sims: 500,
      });
      setSimResult(result);
    } catch {
      setSimResult(null);
    } finally {
      setSimLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPredictions();
  }, [fetchPredictions]);

  return (
    <article className="panel h-full flex flex-col">
      <div className="panel-header">
        <span className="panel-title">Strategy advisor</span>
        <div className="flex gap-1.5">
          {Object.entries(COMPOUND_COLORS)
            .slice(0, 3)
            .map(([name, color]) => (
              <button
                key={name}
                onClick={() => setCurrentCompound(name)}
                className={clsx(
                  "w-5 h-5 rounded-full border-2 transition-all duration-200",
                  currentCompound === name
                    ? "border-race-text scale-110"
                    : "border-transparent opacity-40 hover:opacity-80"
                )}
                style={{ backgroundColor: color }}
                title={name}
                aria-label={`Select ${name} compound`}
              />
            ))}
        </div>
      </div>

      <div className="flex-1 p-3.5 flex flex-col gap-3 overflow-y-auto">
        {loading ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="w-5 h-5 spinner" />
          </div>
        ) : (
          <>
            {/* Tire life gauge */}
            {tirePrediction && (
              <TireLifeGauge
                prediction={tirePrediction}
                compound={currentCompound}
              />
            )}

            {/* Pit window recommendation */}
            {pitWindow && (
              <PitWindowBanner
                optimalLap={pitWindow.optimal_pit_lap}
                compound={pitWindow.recommended_compound}
                modelUsed={pitWindow.model_used}
              />
            )}

            {/* Monte Carlo strategy simulator */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="data-label">Race simulator</span>
                <button
                  onClick={runSimulation}
                  disabled={simLoading}
                  className="pill-btn"
                >
                  {simLoading ? "Simulating…" : "Simulate 500 races"}
                </button>
              </div>

              {simResult ? (
                <div className="flex flex-col gap-1.5 animate-fade-in">
                  <span className="text-data-xs text-race-muted/50 font-mono">
                    Monte Carlo · {simResult.n_sims} sims per plan
                  </span>
                  {simResult.strategies.slice(0, 6).map((s) => (
                    <SimStrategyRow
                      key={s.rank}
                      strategy={s.strategy}
                      rank={s.rank}
                      winProbability={s.win_probability}
                      medianTime={s.median_race_time_s}
                    />
                  ))}
                </div>
              ) : (
                <p className="text-data-xs text-race-muted/40">
                  Simulate thousands of races to find the fastest pit strategy.
                </p>
              )}
            </div>

            {/* Model info */}
            {tirePrediction && (
              <div className="mt-auto pt-2.5 border-t border-race-border/30 flex items-center justify-between">
                <span className="text-data-xs text-race-muted/40 font-mono">
                  Tire model: {tirePrediction.model_name}
                </span>
              </div>
            )}
          </>
        )}
      </div>
    </article>
  );
}
