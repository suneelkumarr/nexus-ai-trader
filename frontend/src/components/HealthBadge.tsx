import type { HealthResponse } from "../types/system";

interface HealthBadgeProps {
  health: HealthResponse | null;
  error: string | null;
  loading: boolean;
}

export function HealthBadge({ health, error, loading }: HealthBadgeProps) {
  if (loading) {
    return <span className="badge badge-neutral">Connecting to Engine...</span>;
  }

  if (error || !health) {
    return (
      <span className="badge badge-error" title={error ?? "Unavailable"}>
        Engine Offline
      </span>
    );
  }

  const healthy = health.status === "ok";
  return (
    <span className={`badge ${healthy ? "badge-ok" : "badge-warn"}`}>
      {healthy ? "PAPER ENGINE ONLINE" : "DEGRADED"} · {health.trading_mode.toUpperCase()} /{" "}
      {health.market_type.toUpperCase()}
    </span>
  );
}

