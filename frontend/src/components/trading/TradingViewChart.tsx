import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  ColorType,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
  type SeriesMarker,
  type CandlestickData,
  type LineData,
  type HistogramData,
  type Time,
} from "lightweight-charts";
import {
  Activity,
  Maximize2,
  Minimize2,
  RefreshCw,
  TrendingUp,
  Layers,
  Sparkles,
} from "lucide-react";
import { fetchCandleSeries } from "../../services/apiClient";
import type { TerminalSnapshotResponse, CandleBarDto } from "../../types/system";

interface TradingViewChartProps {
  snapshot: TerminalSnapshotResponse | null;
  initialSymbol?: string;
}

const POPULAR_SYMBOLS = [
  "BTC/USDT",
  "ETH/USDT",
  "SOL/USDT",
  "BNB/USDT",
  "XRP/USDT",
  "DOGE/USDT",
  "SUI/USDT",
  "PEPE/USDT",
  "AVAX/USDT",
  "LINK/USDT",
  "NEAR/USDT",
  "FET/USDT",
] as const;

const TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"] as const;

function calculateEMA(
  candles: CandleBarDto[],
  period: number,
): LineData<UTCTimestamp>[] {
  if (candles.length < period) return [];
  const k = 2 / (period + 1);
  const emaData: LineData<UTCTimestamp>[] = [];

  let sum = 0;
  for (let i = 0; i < period; i++) {
    sum += candles[i].close;
  }
  let prevEma = sum / period;
  emaData.push({
    time: candles[period - 1].time as UTCTimestamp,
    value: Number(prevEma.toFixed(4)),
  });

  for (let i = period; i < candles.length; i++) {
    const curClose = candles[i].close;
    const curEma = curClose * k + prevEma * (1 - k);
    emaData.push({
      time: candles[i].time as UTCTimestamp,
      value: Number(curEma.toFixed(4)),
    });
    prevEma = curEma;
  }
  return emaData;
}

export function TradingViewChart({
  snapshot,
  initialSymbol = "BTC/USDT",
}: TradingViewChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartApiRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick", Time> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram", Time> | null>(null);
  const ema20SeriesRef = useRef<ISeriesApi<"Line", Time> | null>(null);
  const ema50SeriesRef = useRef<ISeriesApi<"Line", Time> | null>(null);
  const markersPluginRef = useRef<ReturnType<typeof createSeriesMarkers<Time>> | null>(null);

  const [symbol, setSymbol] = useState<string>(initialSymbol);
  const [timeframe, setTimeframe] = useState<string>("15m");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Indicators toggles
  const [showEMA20, setShowEMA20] = useState<boolean>(true);
  const [showEMA50, setShowEMA50] = useState<boolean>(true);
  const [showVolume, setShowVolume] = useState<boolean>(true);
  const [showSignals, setShowSignals] = useState<boolean>(true);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);

  // Live hover inspection bar
  const [hoveredCandle, setHoveredCandle] = useState<CandleBarDto | null>(null);
  const [rawCandles, setRawCandles] = useState<CandleBarDto[]>([]);

  // Find ticker for active symbol in snapshot
  const currentTicker = useMemo(() => {
    return snapshot?.tickers.find((t) => t.symbol === symbol) ?? null;
  }, [snapshot?.tickers, symbol]);

  const currentPrice = currentTicker ? Number(currentTicker.last) : (rawCandles[rawCandles.length - 1]?.close ?? 0);
  const prevPrice = rawCandles[rawCandles.length - 2]?.close ?? currentPrice;
  const priceChangePct = prevPrice > 0 ? ((currentPrice - prevPrice) / prevPrice) * 100 : 0;

  // Filter signals for this symbol
  const relevantSignals = useMemo(() => {
    if (!snapshot?.latest_signals) return [];
    return snapshot.latest_signals.filter((s) => s.symbol === symbol);
  }, [snapshot?.latest_signals, symbol]);

  // Initialize and mount Chart
  useEffect(() => {
    const container = chartContainerRef.current;
    if (!container) return;

    // Clean up previous instance
    if (chartApiRef.current) {
      chartApiRef.current.remove();
      chartApiRef.current = null;
    }

    const chart = createChart(container, {
      width: container.clientWidth || 800,
      height: container.clientHeight || 460,
      layout: {
        background: { type: ColorType.Solid, color: "#050814" },
        textColor: "#94a3b8",
        fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.04)" },
        horzLines: { color: "rgba(255, 255, 255, 0.04)" },
      },
      crosshair: {
        mode: 1, // CrosshairMode.Normal
        vertLine: {
          color: "rgba(0, 229, 255, 0.4)",
          width: 1,
          style: 3, // LineStyle.Dashed
          labelBackgroundColor: "#0f172a",
        },
        horzLine: {
          color: "rgba(0, 229, 255, 0.4)",
          width: 1,
          style: 3,
          labelBackgroundColor: "#0f172a",
        },
      },
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.08)",
        textColor: "#cbd5e1",
        autoScale: true,
        scaleMargins: {
          top: 0.1,
          bottom: 0.22, // Reserve bottom for volume
        },
      },
      timeScale: {
        borderColor: "rgba(255, 255, 255, 0.08)",
        timeVisible: true,
        secondsVisible: false,
      },
    });

    // 1. Candlestick Series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#00E5FF", // Cyan glow bull
      downColor: "#F43F5E", // Rose bear
      borderUpColor: "#00E5FF",
      borderDownColor: "#F43F5E",
      wickUpColor: "#00E5FF",
      wickDownColor: "#F43F5E",
    });

    // 2. Volume Series (Histogram pinned to bottom scale)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: {
        top: 0.78,
        bottom: 0,
      },
    });

    // 3. Technical Indicators
    const ema20Series = chart.addSeries(LineSeries, {
      color: "#00E5FF", // Neon Cyan
      lineWidth: 2,
      crosshairMarkerVisible: true,
      title: "EMA 20",
    });

    const ema50Series = chart.addSeries(LineSeries, {
      color: "#A855F7", // Neon Purple
      lineWidth: 2,
      crosshairMarkerVisible: true,
      title: "EMA 50",
    });

    // 4. Series Markers Plugin
    const markersPlugin = createSeriesMarkers(candleSeries, []);

    // 5. Crosshair Move Handler
    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.seriesData.size) {
        setHoveredCandle(null);
        return;
      }
      const data = param.seriesData.get(candleSeries) as CandlestickData<Time> | undefined;
      const volData = param.seriesData.get(volumeSeries) as HistogramData<Time> | undefined;
      if (data) {
        setHoveredCandle({
          time: Number(param.time),
          open: Number(data.open),
          high: Number(data.high),
          low: Number(data.low),
          close: Number(data.close),
          volume: volData ? Number(volData.value) : 0,
        });
      }
    });

    chartApiRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    ema20SeriesRef.current = ema20Series;
    ema50SeriesRef.current = ema50Series;
    markersPluginRef.current = markersPlugin;

    // Responsive resize observer
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.contentRect && chartApiRef.current) {
          chartApiRef.current.applyOptions({
            width: entry.contentRect.width,
            height: entry.contentRect.height,
          });
        }
      }
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartApiRef.current = null;
    };
  }, []);

  // Fetch candle data when symbol or timeframe changes
  const loadCandleData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchCandleSeries({
        symbol,
        timeframe,
        limit: 250,
      });

      if (!response.candles || response.candles.length === 0) {
        setError(`No historical candles available for ${symbol} (${timeframe})`);
        setLoading(false);
        return;
      }

      setRawCandles(response.candles);

      // Format for lightweight-charts
      const candleData: CandlestickData<UTCTimestamp>[] = response.candles.map((c) => ({
        time: c.time as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }));

      const volumeData: HistogramData<UTCTimestamp>[] = response.candles.map((c) => ({
        time: c.time as UTCTimestamp,
        value: c.volume,
        color: c.close >= c.open ? "rgba(0, 229, 255, 0.35)" : "rgba(244, 63, 94, 0.35)",
      }));

      if (candleSeriesRef.current) {
        candleSeriesRef.current.setData(candleData);
      }
      if (volumeSeriesRef.current) {
        volumeSeriesRef.current.setData(volumeData);
      }

      // Compute & update EMAs
      const ema20 = calculateEMA(response.candles, 20);
      const ema50 = calculateEMA(response.candles, 50);

      if (ema20SeriesRef.current) {
        ema20SeriesRef.current.setData(ema20);
      }
      if (ema50SeriesRef.current) {
        ema50SeriesRef.current.setData(ema50);
      }

      // Fit chart content
      if (chartApiRef.current) {
        chartApiRef.current.timeScale().fitContent();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load candle series");
    } finally {
      setLoading(false);
    }
  }, [symbol, timeframe]);

  // Load candle data on change
  useEffect(() => {
    void loadCandleData();
  }, [loadCandleData]);

  // Update visibility of technical indicator series
  useEffect(() => {
    if (ema20SeriesRef.current) {
      ema20SeriesRef.current.applyOptions({ visible: showEMA20 });
    }
    if (ema50SeriesRef.current) {
      ema50SeriesRef.current.applyOptions({ visible: showEMA50 });
    }
    if (volumeSeriesRef.current) {
      volumeSeriesRef.current.applyOptions({ visible: showVolume });
    }
  }, [showEMA20, showEMA50, showVolume]);

  // Map strategy signals to markers on chart
  useEffect(() => {
    if (!markersPluginRef.current || !rawCandles.length) return;

    if (!showSignals || relevantSignals.length === 0) {
      markersPluginRef.current.setMarkers([]);
      return;
    }

    const markers: SeriesMarker<Time>[] = [];
    // Convert signal timestamps to closest candle times
    for (const sig of relevantSignals) {
      const sigSec = Math.floor(new Date(sig.timestamp).getTime() / 1000);
      // Find closest candle timestamp
      let closestCandle = rawCandles[0];
      let minDiff = Math.abs(rawCandles[0].time - sigSec);
      for (const c of rawCandles) {
        const diff = Math.abs(c.time - sigSec);
        if (diff < minDiff) {
          minDiff = diff;
          closestCandle = c;
        }
      }

      const isLong = sig.direction === "long";
      markers.push({
        time: closestCandle.time as UTCTimestamp,
        position: isLong ? "belowBar" : "aboveBar",
        color: isLong ? "#10B981" : "#F43F5E",
        shape: isLong ? "arrowUp" : "arrowDown",
        text: isLong ? "AI BUY" : "AI EXIT",
        size: 1,
      });
    }

    // Sort markers by time ascending
    markers.sort((a, b) => Number(a.time) - Number(b.time));
    markersPluginRef.current.setMarkers(markers);
  }, [showSignals, relevantSignals, rawCandles]);

  // Real-time tick update from websocket
  useEffect(() => {
    if (!currentTicker || !candleSeriesRef.current || rawCandles.length === 0) return;

    const lastCandle = rawCandles[rawCandles.length - 1];
    const newPrice = Number(currentTicker.last);
    if (!newPrice || isNaN(newPrice)) return;

    const updatedCandle: CandlestickData<UTCTimestamp> = {
      time: lastCandle.time as UTCTimestamp,
      open: lastCandle.open,
      high: Math.max(lastCandle.high, newPrice),
      low: Math.min(lastCandle.low, newPrice),
      close: newPrice,
    };

    candleSeriesRef.current.update(updatedCandle);
  }, [currentTicker, rawCandles]);

  const activeCandle = hoveredCandle ?? rawCandles[rawCandles.length - 1] ?? null;

  return (
    <div
      className={`glass-card flex flex-col rounded-xl border border-white/[0.08] bg-[#050814]/90 backdrop-blur-2xl transition-all duration-300 ${
        isFullscreen ? "fixed inset-2 z-50 overflow-hidden shadow-2xl" : "h-[540px] w-full"
      }`}
    >
      {/* Chart Top Control Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.06] bg-white/[0.02] px-4 py-2.5">
        {/* Left: Symbol & Timeframe pills */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Symbol Selector Pills */}
          <div className="flex items-center rounded-lg border border-white/[0.08] bg-[#0b1022]/80 p-0.5 shadow-inner">
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="bg-transparent px-2.5 py-1 font-mono text-xs font-semibold text-cyan-300 outline-none cursor-pointer"
            >
              {POPULAR_SYMBOLS.map((s) => (
                <option key={s} value={s} className="bg-slate-900 text-slate-200">
                  {s}
                </option>
              ))}
            </select>
          </div>

          {/* Timeframe Selector Pills */}
          <div className="flex items-center rounded-lg border border-white/[0.08] bg-[#0b1022]/80 p-0.5">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                type="button"
                onClick={() => setTimeframe(tf)}
                className={`rounded px-2 py-0.5 font-mono text-[11px] font-medium transition ${
                  timeframe === tf
                    ? "bg-cyan-500/20 text-cyan-300 shadow-[0_0_8px_rgba(0,229,255,0.4)]"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Price Readout */}
          <div className="flex items-center gap-2 pl-2">
            <span className="font-mono text-sm font-bold tracking-tight text-white tabular-nums">
              ${currentPrice >= 10 ? currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : currentPrice.toFixed(4)}
            </span>
            <span
              className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold tabular-nums ${
                priceChangePct >= 0
                  ? "bg-emerald-500/15 text-emerald-300"
                  : "bg-rose-500/15 text-rose-300"
              }`}
            >
              {priceChangePct >= 0 ? "+" : ""}
              {priceChangePct.toFixed(2)}%
            </span>
          </div>
        </div>

        {/* Right: Technical Indicators & Fullscreen */}
        <div className="flex items-center gap-1.5">
          {/* EMA 20 Toggle */}
          <button
            type="button"
            onClick={() => setShowEMA20(!showEMA20)}
            className={`flex items-center gap-1 rounded-md px-2 py-1 font-mono text-[10px] font-medium transition ${
              showEMA20
                ? "border border-cyan-500/40 bg-cyan-500/10 text-cyan-300"
                : "border border-white/[0.05] bg-transparent text-slate-500 hover:text-slate-400"
            }`}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
            EMA 20
          </button>

          {/* EMA 50 Toggle */}
          <button
            type="button"
            onClick={() => setShowEMA50(!showEMA50)}
            className={`flex items-center gap-1 rounded-md px-2 py-1 font-mono text-[10px] font-medium transition ${
              showEMA50
                ? "border border-purple-500/40 bg-purple-500/10 text-purple-300"
                : "border border-white/[0.05] bg-transparent text-slate-500 hover:text-slate-400"
            }`}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-purple-400" />
            EMA 50
          </button>

          {/* Volume Toggle */}
          <button
            type="button"
            onClick={() => setShowVolume(!showVolume)}
            className={`flex items-center gap-1 rounded-md px-2 py-1 font-mono text-[10px] font-medium transition ${
              showVolume
                ? "border border-slate-500/40 bg-slate-500/10 text-slate-300"
                : "border border-white/[0.05] bg-transparent text-slate-500 hover:text-slate-400"
            }`}
          >
            <Layers className="h-3 w-3" />
            VOL
          </button>

          {/* Signals Toggle */}
          <button
            type="button"
            onClick={() => setShowSignals(!showSignals)}
            className={`flex items-center gap-1 rounded-md px-2 py-1 font-mono text-[10px] font-medium transition ${
              showSignals
                ? "border border-amber-500/40 bg-amber-500/10 text-amber-300"
                : "border border-white/[0.05] bg-transparent text-slate-500 hover:text-slate-400"
            }`}
          >
            <Sparkles className="h-3 w-3" />
            SIGNALS ({relevantSignals.length})
          </button>

          {/* Reset / Fit View */}
          <button
            type="button"
            onClick={() => chartApiRef.current?.timeScale().fitContent()}
            title="Reset Scale"
            className="rounded-md border border-white/[0.08] p-1.5 text-slate-400 transition hover:bg-white/[0.05] hover:text-white"
          >
            <RefreshCw className="h-3 w-3" />
          </button>

          {/* Fullscreen Toggle */}
          <button
            type="button"
            onClick={() => setIsFullscreen(!isFullscreen)}
            title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
            className="rounded-md border border-white/[0.08] p-1.5 text-slate-400 transition hover:bg-white/[0.05] hover:text-white"
          >
            {isFullscreen ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
          </button>
        </div>
      </div>

      {/* Candle Inspection HUD Banner */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/[0.04] bg-[#03060f]/60 px-4 py-1.5 font-mono text-[11px]">
        {activeCandle ? (
          <div className="flex flex-wrap items-center gap-4 text-slate-400">
            <div>
              <span className="text-slate-500">O: </span>
              <span className="text-slate-200 tabular-nums">${activeCandle.open}</span>
            </div>
            <div>
              <span className="text-slate-500">H: </span>
              <span className="text-emerald-400 tabular-nums">${activeCandle.high}</span>
            </div>
            <div>
              <span className="text-slate-500">L: </span>
              <span className="text-rose-400 tabular-nums">${activeCandle.low}</span>
            </div>
            <div>
              <span className="text-slate-500">C: </span>
              <span
                className={`font-semibold tabular-nums ${
                  activeCandle.close >= activeCandle.open ? "text-cyan-300" : "text-rose-400"
                }`}
              >
                ${activeCandle.close}
              </span>
            </div>
            <div>
              <span className="text-slate-500">Vol: </span>
              <span className="text-slate-300 tabular-nums">{activeCandle.volume.toLocaleString()}</span>
            </div>
          </div>
        ) : (
          <span className="text-slate-500">Hover crosshair over bars for OHLCV telemetry</span>
        )}

        <div className="flex items-center gap-2 text-[10px] text-slate-500">
          <span className="flex h-1.5 w-1.5 rounded-full bg-cyan-400 shadow-[0_0_6px_rgba(0,229,255,0.8)]" />
          <span>CCXT ZERO-LATENCY FEED</span>
        </div>
      </div>

      {/* Main Chart Canvas Area */}
      <div className="relative flex-1 w-full overflow-hidden bg-[#050814]">
        {loading && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-[#050814]/80 backdrop-blur-sm">
            <Activity className="h-6 w-6 animate-spin text-cyan-400 mb-2" />
            <span className="font-mono text-xs text-cyan-300">Synchronizing candlestick matrix...</span>
          </div>
        )}

        {error && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#050814]/90 p-4">
            <div className="max-w-md rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 font-mono text-xs text-amber-300">
              {error}
            </div>
          </div>
        )}

        <div ref={chartContainerRef} className="h-full w-full" />
      </div>

      {/* Bottom Chart Footer Strip */}
      <div className="flex items-center justify-between border-t border-white/[0.06] bg-[#02040a]/80 px-4 py-1.5 font-mono text-[10px] text-slate-500">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1 text-slate-400">
            <TrendingUp className="h-3 w-3 text-cyan-400" />
            {symbol} • {timeframe.toUpperCase()}
          </span>
          <span>•</span>
          <span>BARS: {rawCandles.length}</span>
          <span>•</span>
          <span className="text-cyan-400/80">EMA 20/50 GOLDEN CROSS RADAR</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-slate-400">TRADINGVIEW LIGHTWEIGHT-CHARTS ENGINE</span>
        </div>
      </div>
    </div>
  );
}
