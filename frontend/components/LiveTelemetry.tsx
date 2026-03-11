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
    <div className="flex flex-col items-center gap-1">
      <div className={clsx("relative", sizeClasses[size])}>
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          <circle
            cx="50"
            cy="50"
            r="40"
            fill="none"
            stroke="#2a2a2a"
            strokeWidth="6"
          />
          <circle
            cx="50"
            cy="50"
            r="40"
            fill="none"
            stroke={color}
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            className="transition-all duration-100"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={clsx("font-mono font-bold text-race-text", fontClasses[size])}>
            {Math.round(value)}
          </span>
          <span className="text-data-xs text-race-muted font-mono">{unit}</span>
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
    <div className="flex items-center gap-2 w-full">
      <span className="data-label w-14 text-right">{label}</span>
      <div className="flex-1 h-3 bg-race-border rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-75"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="font-mono text-data-sm text-race-text w-10 text-right tabular-nums">
        {Math.round(pct)}%
      </span>
    </div>
  );
}

/** Gear indicator with large centered number. */
function GearIndicator({ gear }: { gear: number }) {
  const gearLabel = gear === 0 ? "N" : gear === -1 ? "R" : `${gear}`;
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="w-14 h-14 rounded-lg border-2 border-race-border flex items-center justify-center bg-race-surface">
        <span className="font-mono font-bold text-data-2xl text-telemetry-gear">
          {gearLabel}
        </span>
      </div>
      <span className="data-label">GEAR</span>
    </div>
  );
}

/** DRS indicator light. */
function DrsIndicator({ active }: { active: boolean }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className={clsx(
          "w-14 h-14 rounded-lg border-2 flex items-center justify-center",
          active
            ? "border-telemetry-drs bg-telemetry-drs/20 shadow-glow"
            : "border-race-border bg-race-surface"
        )}
      >
        <span
          className={clsx(
            "font-mono font-bold text-data-md",
            active ? "text-telemetry-drs" : "text-race-muted"
          )}
        >
          DRS
        </span>
      </div>
      <span className="data-label">{active ? "OPEN" : "OFF"}</span>
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
    <div className="flex flex-col gap-1">
      <span className="data-label">{label}</span>
      <div className="h-12 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id={`grad-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.3} />
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
    <div className="panel h-full flex flex-col">
      <div className="panel-header">
        <span className="panel-title">Live Telemetry</span>
        <div className="flex items-center gap-2">
          <div
            className={clsx(
              "w-2 h-2 rounded-full",
              wsState === "connected"
                ? "bg-telemetry-throttle"
                : wsState === "connecting"
                  ? "bg-telemetry-steering animate-pulse"
                  : "bg-telemetry-brake"
            )}
          />
          <span className="text-data-xs font-mono text-race-muted uppercase">
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
            label="SPEED"
            unit="KPH"
            color="#00D4FF"
            size="lg"
          />
          <GearIndicator gear={frame?.gear ?? 0} />
          <DrsIndicator active={(frame?.drs ?? 0) > 0} />
          <Gauge
            value={frame?.rpm ?? 0}
            max={15000}
            label="RPM"
            unit="RPM"
            color="#B388FF"
            size="md"
          />
        </div>

        {/* Pedal bars */}
        <div className="flex flex-col gap-2">
          <PedalBar
            value={frame?.throttle ?? 0}
            label="THROTTLE"
            color="#00FF87"
          />
          <PedalBar
            value={frame?.brake ?? 0}
            label="BRAKE"
            color="#FF3B3B"
          />
        </div>

        {/* Steering */}
        <div className="flex items-center gap-2">
          <span className="data-label w-14 text-right">STEER</span>
          <div className="flex-1 h-3 bg-race-border rounded-full relative overflow-hidden">
            <div
              className="absolute h-full w-2 bg-telemetry-steering rounded-full transition-all duration-75"
              style={{
                left: `${50 + (frame?.steering ?? 0) * 50}%`,
                transform: "translateX(-50%)",
              }}
            />
            <div className="absolute h-full w-px bg-race-muted left-1/2" />
          </div>
          <span className="font-mono text-data-sm text-race-text w-14 text-right tabular-nums">
            {(frame?.steering ?? 0).toFixed(2)}
          </span>
        </div>

        {/* Rolling traces */}
        <div className="flex-1 grid grid-cols-3 gap-3 min-h-0">
          <MiniTrace
            data={traceData}
            dataKey="speed"
            color="#00D4FF"
            label="SPEED"
            max={370}
          />
          <MiniTrace
            data={traceData}
            dataKey="throttle"
            color="#00FF87"
            label="THROTTLE"
            max={100}
          />
          <MiniTrace
            data={traceData}
            dataKey="brake"
            color="#FF3B3B"
            label="BRAKE"
            max={100}
          />
        </div>
      </div>
    </div>
  );
}
