import { onBeforeUnmount, ref } from "vue";

export interface HypothesisAiStreamEvent {
  id: string;
  type: string;
  receivedAt: string;
  payload: Record<string, unknown>;
}

const AI_STREAM_EVENTS = [
  "hypothesis_created",
  "hypothesis_evaluated",
  "ai_insight",
  "ai_weights_updated",
] as const;

export function useHypothesisAiStream() {
  const status = ref<"idle" | "connecting" | "connected" | "reconnecting" | "error">("idle");
  const events = ref<HypothesisAiStreamEvent[]>([]);
  const lastReceivedAt = ref<string | null>(null);
  let source: EventSource | null = null;
  let manuallyClosed = false;

  function pushEvent(type: string, raw: MessageEvent<string>) {
    let payload: Record<string, unknown> = {};
    try {
      const parsed = JSON.parse(raw.data) as { payload?: Record<string, unknown> };
      payload = parsed.payload ?? {};
    } catch {
      payload = { raw: raw.data };
    }

    const entry: HypothesisAiStreamEvent = {
      id: `${type}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      type,
      receivedAt: new Date().toISOString(),
      payload,
    };

    lastReceivedAt.value = entry.receivedAt;
    events.value = [entry, ...events.value].slice(0, 20);
  }

  function connect() {
    if (source) {
      return;
    }

    manuallyClosed = false;
    status.value = "connecting";
    source = new EventSource("/api/v1/hypothesis/sse/ai");

    source.onopen = () => {
      status.value = "connected";
    };

    source.onerror = () => {
      if (manuallyClosed) {
        return;
      }
      status.value = status.value === "connected" ? "reconnecting" : "error";
    };

    for (const eventType of AI_STREAM_EVENTS) {
      source.addEventListener(eventType, (event) => {
        pushEvent(eventType, event as MessageEvent<string>);
      });
    }
  }

  function disconnect() {
    manuallyClosed = true;
    source?.close();
    source = null;
    status.value = "idle";
  }

  onBeforeUnmount(() => {
    disconnect();
  });

  return {
    connect,
    disconnect,
    events,
    lastReceivedAt,
    status,
  };
}
