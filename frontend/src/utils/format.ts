export function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "No data";
  }

  const abs = Math.abs(value);
  const fractionDigits = abs >= 1000 ? 0 : abs >= 1 ? 2 : 4;

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: fractionDigits,
  }).format(value);
}

export function formatCompactNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "No data";
  }

  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatPercent(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "No data";
  }

  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function formatCurrencyDelta(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "No data";
  }

  const sign = value > 0 ? "+" : "";
  return `${sign}${formatCurrency(value)}`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "No data";
  }

  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatDurationSeconds(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value) || value <= 0) {
    return "now";
  }

  const totalSeconds = Math.round(value);
  if (totalSeconds < 60) {
    return `${totalSeconds}s`;
  }

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) {
    return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;
  }

  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  return restMinutes > 0 ? `${hours}h ${restMinutes}m` : `${hours}h`;
}

export function formatRateLimitPolicy(
  requestsPerWindow: number | null | undefined,
  windowSeconds: number | null | undefined,
  requestCost: number | null | undefined,
): string {
  const cost = requestCost ?? 1;
  if (!requestsPerWindow || !windowSeconds) {
    return cost > 1 ? `cost ${cost}` : "adaptive";
  }

  return cost > 1
    ? `${requestsPerWindow}/${windowSeconds}s · cost ${cost}`
    : `${requestsPerWindow}/${windowSeconds}s`;
}

export function formatSignalType(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function formatMarketRegime(value: string | null | undefined): string {
  if (!value) {
    return "Pending";
  }

  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function formatActivityBucket(value: string | null | undefined): string {
  if (!value) {
    return "Pending";
  }

  return value.toUpperCase();
}

export function formatTrend(value: string | null | undefined): string {
  if (!value) {
    return "Pending";
  }

  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function timeframeToLabel(value: number | string): string {
  if (typeof value === "string") {
    return value;
  }

  const mapping: Record<number, string> = {
    15: "15m",
    60: "1h",
    240: "4h",
    1440: "1d",
  };

  return mapping[value] ?? `${value}m`;
}
