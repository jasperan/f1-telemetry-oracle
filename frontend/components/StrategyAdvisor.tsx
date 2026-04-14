"use client";

import { useCallback, useEffect, useState } from "react";
import clsx from "clsx";
import { useStore, TirePrediction, PitStrategy } from "@/lib/store";

/** Tire compound color lookup. */
const COMPOUND_COLORS: Record<string, string> = {
  SOFT: "#e05555",
  MEDIUM: "#d4a845",
  HARD: "#e8e8ed",
  INTERMEDIATE: "#45d48a",
  WET: "#4ca8e0",
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
        "rounded-xl border p-3 transition-all duration-300",
        isOptimal
          ? "border-accent-primary/30 bg-accent-primary/5 shadow-glow"
          : "border-race-border/40 bg-race-surface/60 hover:bg-race-surface/80 hover:border-race-border/60"
      )}
    >
      <div className="flex items-center justify-between mb-2.5">
        <div className="flex items-center gap-2">
          {isOptimal && (
            <span className="text-[0.6rem] font-mono text-accent-primary uppercase tracking-wider font-semibold">
              Optimal
            </span>
          )}
          <span className="font-mono text-data-sm text-race-text font-medium">
            {strategy.strategy_name}
          </span>
        </div>
        <span className="font-mono text-data-xs text-race-muted/60">
          {probPct}%
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2">
        {/* Pit lap */}
        <div className="text-center">
          <span className="data-label block mb-0.5">Pit lap</span>
          <span className="font-mono text-data-md text-race-text font-medium">
            {strategy.pit_lap}
          </span>
        </div>

        {/* Next compound */}
        <div className="text-center">
          <span className="data-label block mb-0.5">Compound</span>
          <div className="flex items-center justify-center gap-1.5 mt-0.5">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: compoundColor, boxShadow: `0 0 4px ${compoundColor}30` }}
            />
            <span className="font-mono text-data-sm text-race-text uppercase font-medium">
              {strategy.next_compound.charAt(0)}
            </span>
          </div>
        </div>

        {/* Time loss */}
        <div className="text-center">
          <span className="data-label block mb-0.5">Time loss</span>
          <span className="font-mono text-data-md text-accent-negative">
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
    <div className="bg-accent-primary/8 border border-accent-primary/20 rounded-xl px-3.5 py-2.5 flex items-center gap-3 animate-fade-in">
      <div className="w-8 h-8 rounded-lg border border-accent-primary/40 flex items-center justify-center bg-accent-primary/10">
        <span className="font-mono text-data-sm text-accent-primary font-bold">
          P
        </span>
      </div>
      <div>
        <span className="text-data-xs text-race-muted/60 font-medium">Recommended pit</span>
        <div className="font-mono text-data-lg text-race-text font-semibold">
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

  const optimalStrategy = pitStrategies.length > 0
    ? pitStrategies.reduce(
        (best, s) => (s.probability > best.probability ? s : best),
        pitStrategies[0]
      )
    : null;

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
            {optimalStrategy && (
              <PitWindowBanner optimalLap={optimalStrategy.pit_lap} />
            )}

            {/* Strategy options */}
            <div className="flex flex-col gap-2">
              <span className="data-label">Strategy options</span>
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
              <div className="mt-auto pt-2.5 border-t border-race-border/30">
                <span className="text-data-xs text-race-muted/40 font-mono">
                  Model: {tirePrediction.model_name}
                </span>
              </div>
            )}
          </>
        )}
      </div>
    </article>
  );
}
