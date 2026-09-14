"use client";

import { useStore } from "@/lib/store";

export default function ConnectionStatus() {
  const connected = useStore((state) => state.wsConnected);
  return (
    <span
      className={`race-connection ${connected ? "is-connected" : ""}`}
      role="status"
    >
      <i aria-hidden="true" />
      {connected ? "Telemetry connected" : "Awaiting telemetry"}
    </span>
  );
}
