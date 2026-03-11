"use client";

import type { SessionInfo, LapSummary } from "./store";

const BASE_URL = "";

/** Generic fetch helper with error handling. */
async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!res.ok) {
    const errorText = await res.text().catch(() => "Unknown error");
    throw new Error(`API ${res.status}: ${errorText}`);
  }

  return res.json();
}

/** Fetch all available sessions. */
export async function fetchSessions(): Promise<SessionInfo[]> {
  return apiFetch<SessionInfo[]>("/api/sessions");
}

/** Fetch laps for a session, optionally filtered by driver. */
export async function fetchLaps(
  sessionId: string,
  driverCode?: string
): Promise<LapSummary[]> {
  const params = new URLSearchParams({ session_id: sessionId });
  if (driverCode) params.set("driver_code", driverCode);
  return apiFetch<LapSummary[]>(`/api/laps?${params}`);
}

/** Fetch telemetry frames for a specific lap. */
export async function fetchTelemetry(
  lapId: string
): Promise<{ frames: Array<Record<string, number>> }> {
  return apiFetch(`/api/laps/${lapId}/telemetry`);
}

/** Send a chat message (non-streaming). */
export async function sendChatMessage(
  message: string,
  includeTelemetry = true
): Promise<{
  response: string;
  intent: string;
  entities: Record<string, unknown>;
  sources: Record<string, number>;
  elapsed_ms: number;
}> {
  return apiFetch("/api/chat/message", {
    method: "POST",
    body: JSON.stringify({
      message,
      include_telemetry: includeTelemetry,
    }),
  });
}

/** Fetch sim vs real comparison data for a lap. */
export async function fetchSimVsReal(
  lapId: string
): Promise<Record<string, unknown>> {
  return apiFetch(`/api/compare/sim-vs-real?lap=${lapId}`);
}

/** Fetch tire life prediction. */
export async function fetchTireLife(params: {
  lap_id: string;
  tire_compound: string;
  tire_age_laps: number;
  track_temp_c: number;
  fuel_load_kg: number;
}): Promise<Record<string, unknown>> {
  return apiFetch("/api/predict/tire-life", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/** Fetch pit window prediction. */
export async function fetchPitWindow(
  lapId: string
): Promise<Record<string, unknown>> {
  return apiFetch("/api/predict/pit-window", {
    method: "POST",
    body: JSON.stringify({ lap_id: lapId }),
  });
}

/** Fetch circuit geometry for 3D track map. */
export async function fetchCircuitGeometry(
  circuitId = "current"
): Promise<{ points: Array<[number, number, number]> }> {
  return apiFetch(`/api/circuits/${circuitId}/geometry`);
}
