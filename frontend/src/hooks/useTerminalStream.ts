import { useCallback, useEffect, useRef, useState } from "react";
import {
  buildTerminalWebSocketUrl,
  fetchTerminalSnapshot,
  triggerEmergencyStop,
} from "../services/apiClient";
import type {
  EmergencyStopResponse,
  TerminalSnapshotResponse,
  WebSocketStatus,
} from "../types/system";

export interface UseTerminalStreamResult {
  snapshot: TerminalSnapshotResponse | null;
  wsStatus: WebSocketStatus;
  loading: boolean;
  error: string | null;
  lastUpdatedAt: string | null;
  emergencyPending: boolean;
  lastEmergencyResponse: EmergencyStopResponse | null;
  refresh: () => Promise<void>;
  activateEmergencyStop: (
    reason: string,
    flattenPositions: boolean,
  ) => Promise<EmergencyStopResponse>;
}

const MAX_BACKOFF_MS = 15_000;
const BASE_BACKOFF_MS = 1_500;

export function useTerminalStream(): UseTerminalStreamResult {
  const [snapshot, setSnapshot] = useState<TerminalSnapshotResponse | null>(null);
  const [wsStatus, setWsStatus] = useState<WebSocketStatus>("connecting");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [emergencyPending, setEmergencyPending] = useState<boolean>(false);
  const [lastEmergencyResponse, setLastEmergencyResponse] =
    useState<EmergencyStopResponse | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef<number>(0);
  const mountedRef = useRef<boolean>(true);

  const applySnapshot = useCallback((next: TerminalSnapshotResponse) => {
    if (!mountedRef.current) {
      return;
    }
    setSnapshot(next);
    setLastUpdatedAt(next.timestamp);
    setError(null);
    setLoading(false);
  }, []);

  const refresh = useCallback(async () => {
    const sock = socketRef.current;
    if (sock && sock.readyState === WebSocket.OPEN) {
      sock.send("refresh");
    }
    try {
      const fresh = await fetchTerminalSnapshot();
      applySnapshot(fresh);
    } catch (err) {
      if (!mountedRef.current) {
        return;
      }
      setError(err instanceof Error ? err.message : "Failed to fetch terminal telemetry");
      setLoading(false);
    }
  }, [applySnapshot]);

  useEffect(() => {
    mountedRef.current = true;
    const controller = new AbortController();

    async function hydrateInitial(): Promise<void> {
      try {
        const initial = await fetchTerminalSnapshot(controller.signal);
        applySnapshot(initial);
      } catch (err) {
        if (controller.signal.aborted || !mountedRef.current) {
          return;
        }
        setError(err instanceof Error ? err.message : "Unable to reach FastAPI backend");
        setLoading(false);
      }
    }

    function clearReconnectTimer(): void {
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    }

    function connectWebSocket(): void {
      if (!mountedRef.current) {
        return;
      }
      clearReconnectTimer();

      setWsStatus((prev) => (prev === "offline" || prev === "reconnecting" ? "reconnecting" : "connecting"));

      let ws: WebSocket;
      try {
        ws = new WebSocket(buildTerminalWebSocketUrl());
      } catch {
        setWsStatus("offline");
        scheduleReconnect();
        return;
      }

      socketRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) {
          ws.close();
          return;
        }
        reconnectAttemptRef.current = 0;
        setWsStatus("live");
        setError(null);
      };

      ws.onmessage = (event: MessageEvent<string>) => {
        if (!mountedRef.current) {
          return;
        }
        try {
          const payload = JSON.parse(event.data) as TerminalSnapshotResponse;
          if (payload && typeof payload.timestamp === "string" && payload.portfolio) {
            applySnapshot(payload);
          }
        } catch {
          // Ignore malformed frames cleanly without throwing UI crashes.
        }
      };

      ws.onerror = () => {
        if (!mountedRef.current) {
          return;
        }
        setWsStatus("reconnecting");
      };

      ws.onclose = () => {
        if (!mountedRef.current) {
          return;
        }
        socketRef.current = null;
        setWsStatus("reconnecting");
        scheduleReconnect();
      };
    }

    function scheduleReconnect(): void {
      if (!mountedRef.current) {
        return;
      }
      clearReconnectTimer();
      const attempt = reconnectAttemptRef.current;
      reconnectAttemptRef.current += 1;
      const delay = Math.min(BASE_BACKOFF_MS * 2 ** attempt, MAX_BACKOFF_MS);
      reconnectTimerRef.current = window.setTimeout(() => {
        connectWebSocket();
      }, delay);
    }

    void hydrateInitial();
    connectWebSocket();

    return () => {
      mountedRef.current = false;
      controller.abort();
      clearReconnectTimer();
      if (socketRef.current) {
        socketRef.current.onclose = null;
        socketRef.current.onerror = null;
        socketRef.current.onmessage = null;
        socketRef.current.onopen = null;
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [applySnapshot]);

  const activateEmergencyStop = useCallback(
    async (reason: string, flattenPositions: boolean): Promise<EmergencyStopResponse> => {
      setEmergencyPending(true);
      try {
        const result = await triggerEmergencyStop({
          reason,
          flatten_positions: flattenPositions,
        });
        if (mountedRef.current) {
          setLastEmergencyResponse(result);
        }
        await refresh();
        return result;
      } finally {
        if (mountedRef.current) {
          setEmergencyPending(false);
        }
      }
    },
    [refresh],
  );

  return {
    snapshot,
    wsStatus,
    loading,
    error,
    lastUpdatedAt,
    emergencyPending,
    lastEmergencyResponse,
    refresh,
    activateEmergencyStop,
  };
}

