"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ReconnectingWebSocket from "reconnecting-websocket";

/** Connection state for WebSocket hooks. */
export type WsState = "connecting" | "connected" | "disconnected" | "error";

/** Options for the useWebSocket hook. */
interface UseWebSocketOptions {
  /** WebSocket URL (e.g., ws://localhost:8000/ws/live) */
  url: string;
  /** Auto-connect on mount (default: true) */
  autoConnect?: boolean;
  /** Ping interval in ms (default: 30000) */
  pingInterval?: number;
  /** Handler for incoming messages */
  onMessage?: (data: unknown) => void;
  /** Handler for connection state changes */
  onStateChange?: (state: WsState) => void;
}

/**
 * React hook for a reconnecting WebSocket connection.
 *
 * Uses reconnecting-websocket for automatic reconnection with
 * exponential backoff. Sends periodic pings to keep the connection alive.
 */
export function useWebSocket({
  url,
  autoConnect = true,
  pingInterval = 30000,
  onMessage,
  onStateChange,
}: UseWebSocketOptions) {
  const wsRef = useRef<ReconnectingWebSocket | null>(null);
  const pingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [state, setState] = useState<WsState>("disconnected");
  const onMessageRef = useRef(onMessage);
  const onStateChangeRef = useRef(onStateChange);

  // Keep refs current
  onMessageRef.current = onMessage;
  onStateChangeRef.current = onStateChange;

  const updateState = useCallback((newState: WsState) => {
    setState(newState);
    onStateChangeRef.current?.(newState);
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current) return;

    updateState("connecting");

    const ws = new ReconnectingWebSocket(url, [], {
      maxReconnectionDelay: 10000,
      minReconnectionDelay: 1000,
      reconnectionDelayGrowFactor: 1.5,
      maxRetries: Infinity,
    });

    ws.onopen = () => {
      updateState("connected");
      // Start ping interval
      pingRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
        }
      }, pingInterval);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data as string);
        if (data.type === "pong") return; // ignore pong responses
        onMessageRef.current?.(data);
      } catch {
        // Non-JSON message — pass raw
        onMessageRef.current?.(event.data);
      }
    };

    ws.onclose = () => {
      updateState("disconnected");
      if (pingRef.current) clearInterval(pingRef.current);
    };

    ws.onerror = () => {
      updateState("error");
    };

    wsRef.current = ws;
  }, [url, pingInterval, updateState]);

  const disconnect = useCallback(() => {
    if (pingRef.current) clearInterval(pingRef.current);
    wsRef.current?.close();
    wsRef.current = null;
    updateState("disconnected");
  }, [updateState]);

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        typeof data === "string" ? data : JSON.stringify(data)
      );
    }
  }, []);

  useEffect(() => {
    if (autoConnect) connect();
    return () => disconnect();
  }, [autoConnect, connect, disconnect]);

  return { state, send, connect, disconnect };
}
