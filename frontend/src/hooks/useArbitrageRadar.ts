import { useEffect, useRef, useState } from "react";
import { frontendConfig } from "../config/env";
import { executePaperArbitrageLeg, fetchArbitrageScan } from "../services/apiClient";
import type { MultiMarketScanResponse } from "../types/arbitrage";

export function useArbitrageRadar() {
  const [scanData, setScanData] = useState<MultiMarketScanResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [executing, setExecuting] = useState<boolean>(false);
  const [lastExecutionResult, setLastExecutionResult] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const isMountedRef = useRef<boolean>(true);

  // Initial fetch via REST
  const refresh = async () => {
    try {
      setLoading(true);
      const data = await fetchArbitrageScan();
      if (isMountedRef.current) {
        setScanData(data);
        setError(null);
      }
    } catch (err) {
      if (isMountedRef.current) {
        setError(err instanceof Error ? err.message : "Failed to scan markets");
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    isMountedRef.current = true;
    refresh();

    // Setup WebSocket stream
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = frontendConfig.apiBaseUrl
      .replace(/^https?:\/\//, "")
      .replace(/\/+$/, "");
    const tokenParam = frontendConfig.apiAuthToken
      ? `?token=${encodeURIComponent(frontendConfig.apiAuthToken)}`
      : "";
    const wsUrl = `${protocol}//${host}/api/v1/arbitrage/ws${tokenParam}`;

    let socket: WebSocket;
    let reconnectTimer: number | undefined;

    const connect = () => {
      try {
        socket = new WebSocket(wsUrl);
        wsRef.current = socket;

        socket.onopen = () => {
          if (isMountedRef.current) {
            setWsConnected(true);
            setError(null);
          }
        };

        socket.onmessage = (event) => {
          try {
            const parsed = JSON.parse(event.data);
            if (parsed.type === "MARKET_RADAR_TICK" && parsed.data) {
              if (isMountedRef.current) {
                setScanData(parsed.data as MultiMarketScanResponse);
                setLoading(false);
              }
            }
          } catch {
            // Ignore parse errors on ping
          }
        };

        socket.onerror = () => {
          if (isMountedRef.current) {
            setWsConnected(false);
          }
        };

        socket.onclose = () => {
          if (isMountedRef.current) {
            setWsConnected(false);
            reconnectTimer = window.setTimeout(connect, 2500);
          }
        };
      } catch {
        if (isMountedRef.current) {
          setWsConnected(false);
          reconnectTimer = window.setTimeout(connect, 3000);
        }
      }
    };

    connect();

    return () => {
      isMountedRef.current = false;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (socket) {
        socket.close();
      }
    };
  }, []);

  const triggerPaperExecution = async (oppId: string, usdtAmount: number = 100) => {
    try {
      setExecuting(true);
      const res = await executePaperArbitrageLeg({
        opportunity_id: oppId,
        allocated_usdt: usdtAmount,
      });
      setLastExecutionResult(
        `Executed ${res.opportunity_id}: Net profit ₹${res.simulated_net_profit_inr} ($${res.simulated_net_profit_usdt})`,
      );
      // Refresh scan
      await refresh();
      return res;
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Execution failed";
      setLastExecutionResult(`Failed: ${msg}`);
      throw err;
    } finally {
      setExecuting(false);
    }
  };

  return {
    scanData,
    loading,
    error,
    wsConnected,
    executing,
    lastExecutionResult,
    refresh,
    triggerPaperExecution,
  };
}

