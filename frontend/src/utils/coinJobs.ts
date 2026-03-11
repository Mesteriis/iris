import type { Coin } from "../services/api";

export type CoinJobState =
  | "ready"
  | "backfilling"
  | "queued"
  | "retry_scheduled"
  | "error"
  | "disabled";

export interface CoinJobSnapshot {
  state: CoinJobState;
  label: string;
  detail: string;
  timestamp: string | null;
}

export function getCoinJobSnapshot(coin: Coin): CoinJobSnapshot {
  const syncError = coin.last_history_sync_error?.trim() ?? "";
  const isPermanentError =
    syncError.includes("No market source supports") ||
    syncError.includes("does not support") ||
    syncError.includes("rejected params");

  if (!coin.enabled) {
    return {
      state: "disabled",
      label: "Disabled",
      detail: "Background sync is disabled for this asset.",
      timestamp: null,
    };
  }

  if (!isPermanentError && coin.next_history_sync_at) {
    return {
      state: "retry_scheduled",
      label: "Retry scheduled",
      detail: syncError.length > 0 ? syncError : "Backfill paused. Next attempt is scheduled.",
      timestamp: coin.next_history_sync_at,
    };
  }

  if (syncError.length > 0) {
    return {
      state: "error",
      label: "Sync error",
      detail: syncError,
      timestamp: coin.next_history_sync_at,
    };
  }

  if (!coin.history_backfill_completed_at) {
    if (coin.last_history_sync_at) {
      return {
        state: "backfilling",
        label: "Backfilling",
        detail: "Historical candles are being loaded.",
        timestamp: coin.last_history_sync_at,
      };
    }

    return {
      state: "queued",
      label: "Queued",
      detail: "Waiting for initial backfill to start.",
      timestamp: null,
    };
  }

  return {
    state: "ready",
    label: "Live sync",
    detail: "Initial backfill completed. Incremental updates are active.",
    timestamp: coin.last_history_sync_at ?? coin.history_backfill_completed_at,
  };
}
