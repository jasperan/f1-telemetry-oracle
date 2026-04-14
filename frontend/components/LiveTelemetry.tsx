"use client";

import { useCallback, useMemo } from "react";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  YAxis,
} from "recharts";
import clsx from "clsx";
import { useWebSocket } from "@/lib/ws";
import { useStore, TelemetryFrame } from "@/lib/store";

/** Circular gauge for speed/RPM display. */
function Gauge({
  value,
  max,
  label,
  unit,
  color,
  size = "md",
}: {
  value: number;
  max: number;
  label: string;
  unit: string;
  color: string;
  size?: "sm" | "md" | "lg";
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const circumference = 2 * Math.PI * 40;
  const dashOffset = circumference * (1 - pct / 100);

  const sizeClasses = {
    sm: "w-16 h-16",
    md: "w-24 h-24",
    lg: "w-32 h-32",
  };

  const fontClasses = {
    sm: "text-data-sm",
    md: "text-data-lg",
    lg: "text-data-2xl",
  };

  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className={clsx("relative", sizeClasses[size])}>
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          <circle
            cx="50"
            cy="50"
            r="40"
            fill="none"
            stroke="var(--color-border)"
            strokeWidth="5"
            opacity="0.5"
          />
          <circle
            cx="50"
            cy="50"
            r="40"
            fill="none"
            stroke={color}
            strokeWidth="5"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            className="transition-all duration-100"
            style={{ filter: `drop-shadow(0 0 4px ${color}40)` }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={clsx("font-mono font-semibold text-race-text", fontClasses[size])}>
            {Math.round(value)}
          </span>
          <span className="text-data-xs text-race-muted/60 font-mono">{unit}</span>
        </div>
      </div>
      <span className="data-label">{label}</span>
    </div>
  );
}

/** Horizontal bar for throttle/brake. */
function PedalBar({
  value,
  label,
  color,
}: {
  value: number;
  label: string;
  color: string;
}) {
  const pct = Math.min(100, Math.max(0, value * 100));
  return (
    <div className="flex items-center gap-2.5 w-full group">
      <span className="data-label w-14 text-right">{label}</span>
      <div className="flex-1 h-2.5 bg-race-border/40 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-75"
          style={{
            width: `${pct}%`,
            backgroundColor: color,
            boxShadow: pct > 50 ? `0 0 8px ${color}30` : "none",
          }}
        />
      </div>
      <span className="font-mono text-data-sm text-race-text w-10 text-right">
        {Math.round(pct)}%
      </span>
    </div>
  );
}

/** Gear indicator with large centered number. */
function GearIndicator({ gear }: { gear: number }) {
  const gearLabel = gear === 0 ? "N" : gear === -1 ? "R" : `${gear}`;
  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className="w-14 h-14 rounded-xl border border-race-border/60 flex items-center justify-center bg-race-surface/80">
        <span className="font-mono font-bold text-data-2xl text-telemetry-gear">
          {gearLabel}
        </span>
      </div>
      <span className="data-label">Gear</span>
    </div>
  );
}

/** DRS indicator light. */
function DrsIndicator({ active }: { active: boolean }) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <div
        className={clsx(
          "w-14 h-14 rounded-xl border flex items-center justify-center transition-all duration-300",
          active
            ? "border-telemetry-drs/60 bg-telemetry-drs/15 shadow-glow"
            : "border-race-border/60 bg-race-surface/80"
        )}
      >
        <span
          className={clsx(
            "font-mono font-bold text-data-md transition-colors duration-300",
            active ? "text-telemetry-drs" : "text-race-muted/50"
          )}
        >
          DRS
        </span>
      </div>
      <span className="data-label">{active ? "Open" : "Off"}</span>
    </div>
  );
}

/** Mini rolling chart for a single telemetry channel. */
function MiniTrace({
  data,
  dataKey,
  color,
  label,
  max,
}: {
  data: Array<Record<string, number>>;
  dataKey: string;
  color: string;
  label: string;
  max: number;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="data-label">{label}</span>
      <div className="h-14 w-full rounded-lg overflow-hidden bg-race-surface/30">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id={`grad-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.2} />
                <stop offset="100%" stopColor={color} stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <YAxis domain={[0, max]} hide />
            <Area
              type="monotone"
              dataKey={dataKey}
              stroke={color}
              fill={`url(#grad-${dataKey})`}
              strokeWidth={1.5}
              isAnimationActive={false}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default function LiveTelemetry() {
  const { currentFrame, recentFrames, setCurrentFrame, setWsConnected } = useStore();

  const onMessage = useCallback(
    (data: unknown) => {
      const frame = data as TelemetryFrame;
      if (frame && typeof frame.speed_kph === "number") {
        setCurrentFrame(frame);
      }
    },
    [setCurrentFrame]
  );

  const { state: wsState } = useWebSocket({
    url: `ws://${typeof window !== "undefined" ? window.location.hostname : "localhost"}:8000/ws/live`,
    onMessage,
    onStateChange: (s) => setWsConnected(s === "connected"),
  });

  // Rolling 10s of data for mini traces (~600 frames at 60Hz)
  const traceData = useMemo(() => {
    const last600 = recentFrames.slice(-600);
    return last600.map((f, i) => ({
      idx: i,
      speed: f.speed_kph,
      throttle: f.throttle * 100,
      brake: f.brake * 100,
    }));
  }, [recentFrames]);

  const frame = currentFrame;

  return (
    <article className="panel h-full flex flex-col">
      <div className="panel-header">
        <span className="panel-title">Live telemetry</span>
        <div className="flex items-center gap-2">
          <div
            className={clsx(
              "w-1.5 h-1.5 rounded-full transition-colors duration-300",
              wsState === "connected"
                ? "bg-accent-positive"
                : wsState === "connecting"
                  ? "bg-accent-warning animate-pulse"
                  : "bg-accent-negative"
            )}
          />
          <span className="text-data-xs font-mono text-race-muted/60 uppercase tracking-wider">
            {wsState}
          </span>
        </div>
      </div>

      <div className="flex-1 p-4 flex flex-col gap-4 overflow-hidden">
        {/* Gauges row */}
        <div className="flex items-center justify-around">
          <Gauge
            value={frame?.speed_kph ?? 0}
            max={370}
            label="Speed"
            unit="KPH"
            color="#4cb8d4"
            size="lg"
          />
          <GearIndicator gear={frame?.gear ?? 0} />
          <DrsIndicator active={(frame?.drs ?? 0) > 0} />
          <Gauge
            value={frame?.rpm ?? 0}
            max={15000}
            label="RPM"
            unit="RPM"
            color="#9b7ee8"
            size="md"
          />
        </div>

        {/* Pedal bars */}
        <div className="flex flex-col gap-2.5">
          <PedalBar
            value={frame?.throttle ?? 0}
            label="Throttle"
            color="#45d48a"
          />
          <PedalBar
            value={frame?.brake ?? 0}
            label="Brake"
            color="#e05555"
          />
        </div>

        {/* Steering */}
        <div className="flex items-center gap-2.5">
          <span className="data-label w-14 text-right">Steer</span>
          <div className="flex-1 h-2.5 bg-race-border/40 rounded-full relative overflow-hidden">
            <div
              className="absolute h-full w-2 bg-telemetry-steering rounded-full transition-all duration-75"
              style={{
                left: `${50 + (frame?.steering ?? 0) * 50}%`,
                transform: "translateX(-50%)",
                boxShadow: "0 0 6px #d4a84540",
              }}
            />
            <div className="absolute h-full w-px bg-race-muted/20 left-1/2" />
          </div>
          <span className="font-mono text-data-sm text-race-text w-14 text-right">
            {(frame?.steering ?? 0).toFixed(2)}
          </span>
        </div>

        {/* Rolling traces */}
        <div className="flex-1 grid grid-cols-3 gap-3 min-h-0">
          <MiniTrace
            data={traceData}
            dataKey="speed"
            color="#4cb8d4"
            label="Speed"
            max={370}
          />
          <MiniTrace
            data={traceData}
            dataKey="throttle"
            color="#45d48a"
            label="Throttle"
            max={100}
          />
          <MiniTrace
            data={traceData}
            dataKey="brake"
            color="#e05555"
            label="Brake"
            max={100}
          />
        </div>
      </div>
    </article>
  );
}
