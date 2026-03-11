"use client";

import { useCallback, useEffect, useState } from "react";
import clsx from "clsx";
import { useStore, TirePrediction, PitStrategy } from "@/lib/store";

/** Tire compound color lookup. */
const COMPOUND_COLORS: Record<string, string> = {
  SOFT: "#FF3B3B",
  MEDIUM: "#FFD700",
  HARD: "#FFFFFF",
  INTERMEDIATE: "#00FF87",
  WET: "#00A3FF",
};

/** Tire life gauge -- circular with cliff risk indicator. */
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
    <div className="flex flex-col items-center gap-2">
      <div className="relative w-32 h-32">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          {/* Background ring */}
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke="#1a1a1a"
            strokeWidth="8"
          />
          {/* Grip level */}
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke={gripPct > 30 ? compoundColor : "#FF3B3B"}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={gripOffset}
            className="transition-all duration-500"
          />
          {/* Cliff risk indicator (inner ring) */}
          {cliffPct > 0 && (
            <circle
              cx="50"
              cy="50"
              r="36"
              fill="none"
              stroke="#FF3B3B"
              strokeWidth="3"
              strokeLinecap="round"
              strokeDasharray={2 * Math.PI * 36}
              strokeDashoffset={2 * Math.PI * 36 * (1 - cliffPct / 100)}
              opacity={0.6}
            />
          )}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono font-bold text-data-2xl text-race-text">
            {Math.round(gripPct)}
          </span>
          <span className="text-data-xs text-race-muted font-mono">GRIP %</span>
        </div>
      </div>

      {/* Compound label */}
      <div className="flex items-center gap-2">
        <div
          className="w-3 h-3 rounded-full"
          style={{ backgroundColor: compoundColor }}
        />
        <span className="font-mono text-data-sm text-race-text uppercase">
          {compound}
        </span>
      </div>

      {/* Laps remaining */}
      <div className="text-center">
        <span className="font-mono text-data-xl text-race-text">
          {prediction.laps_remaining}
        </span>
        <span className="text-data-xs text-race-muted ml-1">laps left</span>
      </div>

      {/* Cliff risk bar */}
      {cliffPct > 0 && (
        <div className="w-full max-w-[160px]">
          <div className="flex justify-between mb-1">
            <span className="data-label">CLIFF RISK</span>
            <span
              className={clsx(
                "font-mono text-data-xs",
                cliffPct > 70
                  ? "text-telemetry-brake"
                  : cliffPct > 40
                    ? "text-telemetry-steering"
                    : "text-race-muted"
              )}
            >
              {Math.round(cliffPct)}%
            </span>
          </div>
          <div className="h-1.5 bg-race-border rounded-full overflow-hidden">
            <div
              className={clsx(
                "h-full rounded-full transition-all duration-500",
                cliffPct > 70
                  ? "bg-telemetry-brake"
                  : cliffPct > 40
                    ? "bg-telemetry-steering"
                    : "bg-race-muted"
              )}
              style={{ width: `${cliffPct}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

/** Single strategy option card. */
function StrategyCard({
  strategy,
  isOptimal,
}: {
  strategy: PitStrategy;
  isOptimal: boolean;
}) {
  const compoundColor =
    COMPOUND_COLORS[strategy.next_compound.toUpperCase()] ?? "#666";
  const probPct = Math.round(strategy.probability * 100);

  return (
    <div
      className={clsx(
        "rounded-lg border p-3 transition-colors",
        isOptimal
          ? "border-telemetry-speed/50 bg-telemetry-speed/5"
          : "border-race-border bg-race-surface"
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          {isOptimal && (
            <span className="text-data-xs font-mono text-telemetry-speed uppercase">
              OPTIMAL
            </span>
          )}
          <span className="font-mono text-data-sm text-race-text">
            {strategy.strategy_name}
          </span>
        </div>
        <span className="font-mono text-data-xs text-race-muted">
          {probPct}%
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2">
        {/* Pit lap */}
        <div className="text-center">
          <span className="data-label block">PIT LAP</span>
          <span className="font-mono text-data-md text-race-text">
            {strategy.pit_lap}
          </span>
        </div>

        {/* Next compound */}
        <div className="text-center">
          <span className="data-label block">COMPOUND</span>
          <div className="flex items-center justify-center gap-1 mt-0.5">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: compoundColor }}
            />
            <span className="font-mono text-data-sm text-race-text uppercase">
              {strategy.next_compound.charAt(0)}
            </span>
          </div>
        </div>

        {/* Time loss */}
        <div className="text-center">
          <span className="data-label block">TIME LOSS</span>
          <span className="font-mono text-data-md text-telemetry-brake">
            +{strategy.expected_time_loss_s.toFixed(1)}s
          </span>
        </div>
      </div>
    </div>
  );
}

/** Pit window recommendation banner. */
function PitWindowBanner({ optimalLap }: { optimalLap: number }) {
  return (
    <div className="bg-telemetry-speed/10 border border-telemetry-speed/30 rounded-lg px-3 py-2 flex items-center gap-3">
      <div className="w-8 h-8 rounded-full border-2 border-telemetry-speed flex items-center justify-center">
        <span className="font-mono text-data-sm text-telemetry-speed font-bold">
          P
        </span>
      </div>
      <div>
        <span className="text-data-xs text-race-muted">RECOMMENDED PIT</span>
        <div className="font-mono text-data-lg text-race-text">
          Lap {optimalLap}
        </div>
      </div>
    </div>
  );
}

export default function StrategyAdvisor() {
  const {
    tirePrediction,
    pitStrategies,
    setTirePrediction,
    setPitStrategies,
    selectedLapIds,
  } = useStore();
  const [loading, setLoading] = useState(false);
  const [currentCompound, setCurrentCompound] = useState("SOFT");

  const fetchPredictions = useCallback(async () => {
    if (!selectedLapIds.length) return;
    setLoading(true);

    try {
      // Fetch tire life prediction
      const tireRes = await fetch("/api/predict/tire-life", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lap_id: selectedLapIds[0],
          tire_compound: currentCompound,
          tire_age_laps: 12,
          track_temp_c: 35.0,
          fuel_load_kg: 80.0,
        }),
      });

      if (tireRes.ok) {
        const tireData: TirePrediction = await tireRes.json();
        setTirePrediction(tireData);
      }

      // Fetch pit window prediction
      const pitRes = await fetch("/api/predict/pit-window", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lap_id: selectedLapIds[0] }),
      });

      if (pitRes.ok) {
        const pitData = await pitRes.json();
        setPitStrategies(pitData.strategies ?? []);
      }
    } catch {
      // Use fallback data for display
      setTirePrediction({
        grip_percent: 72.5,
        laps_remaining: 8,
        cliff_risk: 0.25,
        model_name: "tire_degradation_heuristic",
      });
      setPitStrategies([
        {
          strategy_name: "Optimal 1-stop",
          pit_lap: 22,
          next_compound: "HARD",
          expected_time_loss_s: 22.5,
          probability: 0.65,
        },
        {
          strategy_name: "Aggressive 1-stop",
          pit_lap: 18,
          next_compound: "MEDIUM",
          expected_time_loss_s: 21.8,
          probability: 0.25,
        },
        {
          strategy_name: "2-stop",
          pit_lap: 15,
          next_compound: "SOFT",
          expected_time_loss_s: 44.0,
          probability: 0.1,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [
    selectedLapIds,
    currentCompound,
    setTirePrediction,
    setPitStrategies,
  ]);

  useEffect(() => {
    fetchPredictions();
  }, [fetchPredictions]);

  const optimalStrategy = pitStrategies.reduce(
    (best, s) => (s.probability > best.probability ? s : best),
    pitStrategies[0]
  );

  return (
    <div className="panel h-full flex flex-col">
      <div className="panel-header">
        <span className="panel-title">Strategy Advisor</span>
        <div className="flex gap-1">
          {Object.entries(COMPOUND_COLORS)
            .slice(0, 3)
            .map(([name, color]) => (
              <button
                key={name}
                onClick={() => setCurrentCompound(name)}
                className={clsx(
                  "w-5 h-5 rounded-full border-2 transition-all",
                  currentCompound === name
                    ? "border-race-text scale-110"
                    : "border-transparent opacity-50 hover:opacity-100"
                )}
                style={{ backgroundColor: color }}
                title={name}
              />
            ))}
        </div>
      </div>

      <div className="flex-1 p-3 flex flex-col gap-3 overflow-y-auto">
        {loading ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="w-6 h-6 border-2 border-telemetry-speed border-t-transparent rounded-full animate-spin" />
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
            {optimalStrategy && (
              <PitWindowBanner optimalLap={optimalStrategy.pit_lap} />
            )}

            {/* Strategy options */}
            <div className="flex flex-col gap-2">
              <span className="data-label">STRATEGY OPTIONS</span>
              {pitStrategies.map((strategy, i) => (
                <StrategyCard
                  key={i}
                  strategy={strategy}
                  isOptimal={strategy === optimalStrategy}
                />
              ))}
            </div>

            {/* Model info */}
            {tirePrediction && (
              <div className="mt-auto pt-2 border-t border-race-border">
                <span className="text-data-xs text-race-muted font-mono">
                  Model: {tirePrediction.model_name}
                </span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
