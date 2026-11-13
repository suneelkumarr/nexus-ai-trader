export function toFiniteNumber(value: number | string | null | undefined): number {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : 0;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

export function formatInr(value: number | string | null | undefined, showSign = false): string {
  const num = toFiniteNumber(value);
  const absFormatted = new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(num));

  if (num < 0) {
    return `-₹${absFormatted}`;
  }
  if (showSign && num > 0) {
    return `+₹${absFormatted}`;
  }
  return `₹${absFormatted}`;
}

export function formatUsdt(value: number | string | null | undefined, decimals = 2): string {
  const num = toFiniteNumber(value);
  return `$${new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(num)}`;
}

export function formatPct(value: number | string | null | undefined, showSign = false): string {
  const num = toFiniteNumber(value);
  const prefix = showSign && num > 0 ? "+" : "";
  return `${prefix}${num.toFixed(2)}%`;
}

export function formatQty(value: number | string | null | undefined): string {
  const num = toFiniteNumber(value);
  return num.toFixed(6).replace(/\.?0+$/, (match) => (match.startsWith(".") ? ".00" : ""));
}

export function formatUtcTime(isoString: string | null | undefined): string {
  if (!isoString) {
    return "--";
  }
  const parsed = new Date(isoString);
  if (Number.isNaN(parsed.getTime())) {
    return isoString;
  }
  return parsed.toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

