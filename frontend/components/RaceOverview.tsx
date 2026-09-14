"use client";

import { useStore } from "@/lib/store";

export default function RaceOverview() {
  const session = useStore((state) => state.selectedSession);
  const laps = useStore((state) => state.laps);
  const selectedLapIds = useStore((state) => state.selectedLapIds);
  return (
    <section className="race-overview" aria-labelledby="race-overview-title">
      <div>
        <p>TELEMETRY / STRATEGY / RACE INTELLIGENCE</p>
        <h2 id="race-overview-title">
          Every lap. <span>In context.</span>
        </h2>
      </div>
      <dl>
        <div>
          <dt>Session</dt>
          <dd>{session?.circuit_name || "Awaiting selection"}</dd>
        </div>
        <div>
          <dt>Laps loaded</dt>
          <dd>{laps.length.toString().padStart(2, "0")}</dd>
        </div>
        <div>
          <dt>For comparison</dt>
          <dd>{selectedLapIds.length.toString().padStart(2, "0")}</dd>
        </div>
      </dl>
    </section>
  );
}
