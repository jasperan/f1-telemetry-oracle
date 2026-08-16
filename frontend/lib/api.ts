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
  if (driverCode) params.set("driver_id", driverCode);
  return apiFetch<LapSummary[]>(`/api/laps?${params}`);
}

/** Fetch telemetry frames for a specific lap. */
export async function fetchTelemetry(
  lapId: string
): Promise<{ items: Array<Record<string, number>>; total: number; has_more: boolean }> {
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
  trace: {
    path: string;
    intent?: string;
    tool_calls?: string[];
    iterations?: number;
    sources?: Record<string, number>;
    stages_ms?: Record<string, number>;
  };
}> {
  return apiFetch("/api/chat/message", {
    method: "POST",
    body: JSON.stringify({
      message,
      include_telemetry: includeTelemetry,
    }),
  });
}

/** Run the Monte Carlo pit-strategy simulator. */
export async function fetchStrategySim(params: {
  total_laps: number;
  track_temp_c?: number;
  fuel_start_kg?: number;
  n_sims?: number;
  compounds?: string[];
}): Promise<{
  total_laps: number;
  track_temp_c: number;
  n_sims: number;
  fastest_median_s: number;
  strategies: Array<{
    strategy: string[];
    median_race_time_s: number;
    p10_race_time_s: number;
    p90_race_time_s: number;
    win_probability: number;
    rank: number;
  }>;
}> {
  return apiFetch("/api/predict/strategy-sim", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/** Find the real driver whose driving style most resembles a sim lap. */
export async function fetchDrivingTwin(
  lapId: string
): Promise<{
  lap_id: string;
  error?: string;
  overall_twin?: {
    driver_code: string;
    mean_similarity: number;
    best_sector_similarity: number;
  } | null;
  sectors?: Array<{
    sector: number;
    matches: Array<{
      lap_id: string;
      code: string;
      driver: string;
      lap_time_ms: number | null;
      similarity: number;
    }>;
  }>;
}> {
  return apiFetch(`/api/compare/driving-twin?lap_id=${lapId}&top_k=3`);
}

/** Fetch sim vs real comparison data for a lap. */
export async function fetchSimVsReal(
  lapId: string
): Promise<Record<string, unknown>> {
  return apiFetch(`/api/compare/sim-vs-real?lap_id=${lapId}`);
}

/** Fetch tire life prediction. */
export async function fetchTireLife(params: {
  tire_compound: string;
  tire_age_laps: number;
  avg_speed_kph?: number;
  track_temp_c?: number;
  fuel_load_kg?: number;
}): Promise<Record<string, unknown>> {
  return apiFetch("/api/predict/tire-life", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/** Fetch pit window prediction. */
export async function fetchPitWindow(params: {
  current_lap: number;
  total_laps: number;
  tire_compound: string;
  tire_age_laps: number;
  position?: number;
  gap_ahead_ms?: number;
  gap_behind_ms?: number;
}): Promise<Record<string, unknown>> {
  return apiFetch("/api/predict/pit-window", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

/** Fetch circuit geometry for 3D track map. */
export async function fetchCircuitGeometry(
  circuitId = "current"
): Promise<{ points: Array<[number, number, number]> }> {
  return apiFetch(`/api/circuits/${circuitId}/geometry`);
}
