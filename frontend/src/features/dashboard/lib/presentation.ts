export function formatFusionDecision(decision: string | null | undefined): string {
  if (!decision) {
    return "No decision";
  }

  return decision.replace(/_/g, " ");
}

export function decisionTone(decision: string | null | undefined): string {
  if (decision === "BUY") {
    return "bullish";
  }
  if (decision === "SELL") {
    return "bearish";
  }
  if (decision === "HOLD") {
    return "sideways";
  }
  return "pending";
}

export function predictionTone(status: string | null | undefined): string {
  if (status === "confirmed") {
    return "bullish";
  }
  if (status === "failed") {
    return "bearish";
  }
  if (status === "expired") {
    return "sideways";
  }
  return "pending";
}
