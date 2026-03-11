"use client";

import { create } from "zustand";

// --- Telemetry Types ---

export interface TelemetryFrame {
  timestamp_ms: number;
  distance_m: number;
  speed_kph: number;
  throttle: number;
  brake: number;
  steering: number;
  gear: number;
  rpm: number;
  drs: number;
  pos_x: number;
  pos_y: number;
  pos_z: number;
}

export interface LapSummary {
  lap_id: string;
  lap_number: number;
  lap_time_ms: number;
  sector1_ms: number;
  sector2_ms: number;
  sector3_ms: number;
  tire_compound: string;
  tire_age_laps: number;
  driver_code: string;
  source: "sim" | "openf1" | "ergast";
}

export interface SessionInfo {
  session_id: string;
  circuit_name: string;
  session_type: string;
  source: string;
  started_at: string;
}

// --- Chat Types ---

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  intent?: string;
  entities?: Record<string, unknown>;
  sources?: Record<string, number>;
  elapsed_ms?: number;
  timestamp: number;
}

// --- Strategy Types ---

export interface TirePrediction {
  grip_percent: number;
  laps_remaining: number;
  cliff_risk: number;
  model_name: string;
}

export interface PitStrategy {
  strategy_name: string;
  pit_lap: number;
  next_compound: string;
  expected_time_loss_s: number;
  probability: number;
}

// --- Circuit Types ---

export interface CircuitPoint {
  x: number;
  y: number;
  z: number;
}

// --- Store ---

interface TelemetryStore {
  // Live telemetry
  currentFrame: TelemetryFrame | null;
  recentFrames: TelemetryFrame[];
  setCurrentFrame: (frame: TelemetryFrame) => void;

  // Session
  sessions: SessionInfo[];
  selectedSession: SessionInfo | null;
  setSessions: (sessions: SessionInfo[]) => void;
  selectSession: (session: SessionInfo | null) => void;

  // Laps
  laps: LapSummary[];
  selectedLapIds: string[];
  setLaps: (laps: LapSummary[]) => void;
  toggleLapSelection: (lapId: string) => void;
  clearLapSelection: () => void;

  // Chat
  chatMessages: ChatMessage[];
  isChatStreaming: boolean;
  addChatMessage: (msg: ChatMessage) => void;
  appendToLastMessage: (content: string) => void;
  setChatStreaming: (streaming: boolean) => void;
  clearChat: () => void;

  // Strategy
  tirePrediction: TirePrediction | null;
  pitStrategies: PitStrategy[];
  setTirePrediction: (pred: TirePrediction | null) => void;
  setPitStrategies: (strategies: PitStrategy[]) => void;

  // Circuit
  circuitGeometry: CircuitPoint[];
  carPosition: CircuitPoint | null;
  heatmapOverlay: "speed" | "brake" | "delta" | null;
  setCircuitGeometry: (points: CircuitPoint[]) => void;
  setCarPosition: (pos: CircuitPoint | null) => void;
  setHeatmapOverlay: (overlay: "speed" | "brake" | "delta" | null) => void;

  // Connection
  wsConnected: boolean;
  setWsConnected: (connected: boolean) => void;
}

const MAX_RECENT_FRAMES = 600; // ~10 seconds at 60 Hz

export const useStore = create<TelemetryStore>((set) => ({
  // Live telemetry
  currentFrame: null,
  recentFrames: [],
  setCurrentFrame: (frame) =>
    set((state) => ({
      currentFrame: frame,
      recentFrames: [
        ...state.recentFrames.slice(-(MAX_RECENT_FRAMES - 1)),
        frame,
      ],
    })),

  // Session
  sessions: [],
  selectedSession: null,
  setSessions: (sessions) => set({ sessions }),
  selectSession: (session) => set({ selectedSession: session }),

  // Laps
  laps: [],
  selectedLapIds: [],
  setLaps: (laps) => set({ laps }),
  toggleLapSelection: (lapId) =>
    set((state) => ({
      selectedLapIds: state.selectedLapIds.includes(lapId)
        ? state.selectedLapIds.filter((id) => id !== lapId)
        : [...state.selectedLapIds, lapId],
    })),
  clearLapSelection: () => set({ selectedLapIds: [] }),

  // Chat
  chatMessages: [],
  isChatStreaming: false,
  addChatMessage: (msg) =>
    set((state) => ({
      chatMessages: [...state.chatMessages, msg],
    })),
  appendToLastMessage: (content) =>
    set((state) => {
      const msgs = [...state.chatMessages];
      if (msgs.length > 0 && msgs[msgs.length - 1].role === "assistant") {
        msgs[msgs.length - 1] = {
          ...msgs[msgs.length - 1],
          content: msgs[msgs.length - 1].content + content,
        };
      }
      return { chatMessages: msgs };
    }),
  setChatStreaming: (streaming) => set({ isChatStreaming: streaming }),
  clearChat: () => set({ chatMessages: [] }),

  // Strategy
  tirePrediction: null,
  pitStrategies: [],
  setTirePrediction: (pred) => set({ tirePrediction: pred }),
  setPitStrategies: (strategies) => set({ pitStrategies: strategies }),

  // Circuit
  circuitGeometry: [],
  carPosition: null,
  heatmapOverlay: null,
  setCircuitGeometry: (points) => set({ circuitGeometry: points }),
  setCarPosition: (pos) => set({ carPosition: pos }),
  setHeatmapOverlay: (overlay) => set({ heatmapOverlay: overlay }),

  // Connection
  wsConnected: false,
  setWsConnected: (connected) => set({ wsConnected: connected }),
}));
