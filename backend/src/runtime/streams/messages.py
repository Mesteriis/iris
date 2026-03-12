from __future__ import annotations

import json
import os
import queue
import socket
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from redis import Redis
from redis.exceptions import RedisError, ResponseError

from src.core.settings import get_settings
from src.apps.market_data.domain import utc_now

if TYPE_CHECKING:
    from src.apps.market_data.models import Coin


MESSAGE_STREAM = "iris:analysis_events"
MESSAGE_RECEIVER_GROUPS = {
    "frontend": "frontend",
    "ha": "ha",
}
READ_BLOCK_MILLISECONDS = 1000
PUBLISH_QUEUE_WAIT_SECONDS = 0.25


# NOTE:
# This message bus still uses synchronous Redis primitives intentionally.
# The publish side is isolated behind a background thread, and the receiver side
# is legacy console/debug infrastructure outside the main HTTP request path.
@dataclass(frozen=True, slots=True)
class AnalysisMessage:
    topic: str
    text: str
    coin_symbol: str
    created_at: datetime
    payload: dict[str, Any]


class RedisMessageBus:
    def __init__(self, redis_url: str, *, stream_name: str = MESSAGE_STREAM) -> None:
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._stream_name = stream_name
        self._consumer_name = f"{socket.gethostname()}-{os.getpid()}"
        self._stop_event = threading.Event()
        self._publish_queue: queue.SimpleQueue[dict[str, str] | None] = queue.SimpleQueue()
        self._threads: dict[str, threading.Thread] = {}
        self._receivers: dict[str, tuple[str, str]] = {}
        self._lock = threading.Lock()
        self._publisher_thread = threading.Thread(
            target=self._publish_loop,
            daemon=True,
            name="iris-message-bus-publisher",
        )
        self._publisher_thread.start()

    def _ensure_group(self, group_name: str) -> None:
        try:
            self._redis.xgroup_create(
                name=self._stream_name,
                groupname=group_name,
                id="$",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def _deserialize_message(self, fields: dict[str, str]) -> AnalysisMessage:
        payload_raw = fields.get("payload", "{}")
        payload = json.loads(payload_raw)
        created_at_raw = fields.get("created_at")
        created_at = datetime.fromisoformat(created_at_raw) if created_at_raw else utc_now()
        return AnalysisMessage(
            topic=fields["topic"],
            text=fields["text"],
            coin_symbol=fields["coin_symbol"],
            created_at=created_at,
            payload=payload if isinstance(payload, dict) else {},
        )

    def _consume_group(self, group_name: str, receiver_name: str, consumer_name: str) -> None:
        while not self._stop_event.is_set():
            try:
                entries = self._redis.xreadgroup(
                    groupname=group_name,
                    consumername=consumer_name,
                    streams={self._stream_name: ">"},
                    count=10,
                    block=READ_BLOCK_MILLISECONDS,
                )
            except RedisError as exc:
                if "NOGROUP" in str(exc):
                    try:
                        self._ensure_group(group_name)
                    except RedisError as ensure_exc:
                        print(
                            f"[message-bus][{receiver_name}] group recovery failed: {ensure_exc}",
                            flush=True,
                        )
                        time.sleep(1)
                    continue
                print(f"[message-bus][{receiver_name}] reader error: {exc}", flush=True)
                time.sleep(1)
                continue

            if not entries:
                continue

            for _, messages in entries:
                for message_id, fields in messages:
                    try:
                        message = self._deserialize_message(fields)
                        print(
                            f"[message-bus][{receiver_name}] topic={message.topic} "
                            f"coin={message.coin_symbol} text={message.text}",
                            flush=True,
                        )
                    except Exception as exc:
                        print(
                            f"[message-bus][{receiver_name}] handler failed for "
                            f"{fields.get('topic', 'unknown')} ({fields.get('coin_symbol', 'unknown')}): {exc}",
                            flush=True,
                        )
                    finally:
                        try:
                            self._redis.xack(self._stream_name, group_name, message_id)
                        except RedisError as exc:
                            print(
                                f"[message-bus][{receiver_name}] ack failed for {message_id}: {exc}",
                                flush=True,
                            )

    def _publish_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                fields = self._publish_queue.get(timeout=PUBLISH_QUEUE_WAIT_SECONDS)
            except queue.Empty:
                continue
            if fields is None:
                break
            try:
                self._redis.xadd(self._stream_name, fields=fields)
            except RedisError as exc:  # pragma: no cover
                print(
                    f"[message-bus][publisher] publish failed for {fields.get('topic', 'unknown')}: {exc}",
                    flush=True,
                )

    def start_console_receiver(self, receiver_name: str) -> None:
        with self._lock:
            if receiver_name in self._threads:
                return
            group_name = MESSAGE_RECEIVER_GROUPS[receiver_name]
            consumer_name = f"{receiver_name}-{self._consumer_name}"
            self._ensure_group(group_name)
            thread = threading.Thread(
                target=self._consume_group,
                args=(group_name, receiver_name, consumer_name),
                daemon=True,
                name=f"iris-bus-{receiver_name}",
            )
            self._threads[receiver_name] = thread
            self._receivers[receiver_name] = (group_name, consumer_name)
            thread.start()

    def publish(self, message: AnalysisMessage) -> None:
        fields = {
            "topic": message.topic,
            "text": message.text,
            "coin_symbol": message.coin_symbol,
            "created_at": message.created_at.isoformat(),
            "payload": json.dumps(message.payload, ensure_ascii=True, sort_keys=True),
        }
        self._publish_queue.put(fields)

    def close(self) -> None:
        with self._lock:
            self._stop_event.set()
            self._publish_queue.put(None)
            threads = list(self._threads.values())
            receivers = list(self._receivers.values())
            self._threads.clear()
            self._receivers.clear()

        self._publisher_thread.join(timeout=2.0)
        for thread in threads:
            thread.join(timeout=(READ_BLOCK_MILLISECONDS / 1000) + 1)

        for group_name, consumer_name in receivers:
            try:
                self._redis.xgroup_delconsumer(
                    name=self._stream_name,
                    groupname=group_name,
                    consumername=consumer_name,
                )
            except RedisError:
                pass

        self._redis.close()


_message_bus: RedisMessageBus | None = None


def get_message_bus() -> RedisMessageBus:
    global _message_bus
    if _message_bus is None:
        settings = get_settings()
        _message_bus = RedisMessageBus(settings.redis_url)
    return _message_bus


def reset_message_bus() -> None:
    global _message_bus
    if _message_bus is None:
        return
    _message_bus.close()
    _message_bus = None


def register_default_receivers() -> None:
    bus = get_message_bus()
    for receiver_name in MESSAGE_RECEIVER_GROUPS:
        bus.start_console_receiver(receiver_name)


def _coin_payload(coin: "Coin") -> dict[str, Any]:
    return {
        "coin_id": coin.id,
        "coin_name": coin.name,
        "asset_type": coin.asset_type,
    }


def publish_coin_history_progress_message(
    coin: "Coin",
    *,
    progress_percent: float,
    loaded_points: int,
    total_points: int,
) -> None:
    get_message_bus().publish(
        AnalysisMessage(
            topic="coin.history.progress",
            text=f"History for {coin.symbol} loaded {progress_percent:.1f}%.",
            coin_symbol=coin.symbol,
            created_at=utc_now(),
            payload={
                **_coin_payload(coin),
                "progress_percent": progress_percent,
                "loaded_points": loaded_points,
                "total_points": total_points,
            },
        )
    )


def publish_coin_history_loaded_message(
    coin: "Coin",
    *,
    total_points: int,
) -> None:
    get_message_bus().publish(
        AnalysisMessage(
            topic="coin.history.loaded",
            text=f"History loaded for {coin.symbol}.",
            coin_symbol=coin.symbol,
            created_at=utc_now(),
            payload={
                **_coin_payload(coin),
                "total_points": total_points,
            },
        )
    )


def publish_coin_analysis_messages(coin: "Coin") -> None:
    bus = get_message_bus()
    ready_message = AnalysisMessage(
        topic="coin.ready_for_analysis",
        text=f"Coin {coin.symbol} is ready for analysis.",
        coin_symbol=coin.symbol,
        created_at=utc_now(),
        payload=_coin_payload(coin),
    )
    analysis_started_message = AnalysisMessage(
        topic="analysis.started",
        text=f"Analysis started for {coin.symbol}.",
        coin_symbol=coin.symbol,
        created_at=utc_now(),
        payload=_coin_payload(coin),
    )
    bus.publish(ready_message)
    bus.publish(analysis_started_message)


def publish_investment_decision_message(
    coin: "Coin",
    *,
    timeframe: int,
    decision: str,
    confidence: float,
    score: float,
    reason: str,
) -> None:
    get_message_bus().publish(
        AnalysisMessage(
            topic="iris.decision",
            text=f"Decision {decision} for {coin.symbol}.",
            coin_symbol=coin.symbol,
            created_at=utc_now(),
            payload={
                **_coin_payload(coin),
                "coin": coin.symbol,
                "timeframe": timeframe,
                "decision": decision,
                "confidence": confidence,
                "score": score,
                "reason": reason,
            },
        )
    )


def publish_investment_signal_message(
    coin: "Coin",
    *,
    timeframe: int,
    decision: str,
    confidence: float,
    risk_score: float,
    reason: str,
) -> None:
    get_message_bus().publish(
        AnalysisMessage(
            topic="iris.investment_signal",
            text=f"Investment signal {decision} for {coin.symbol}.",
            coin_symbol=coin.symbol,
            created_at=utc_now(),
            payload={
                **_coin_payload(coin),
                "coin": coin.symbol,
                "timeframe": timeframe,
                "decision": decision,
                "confidence": confidence,
                "risk_score": risk_score,
                "risk_adjusted_score": risk_score,
                "reason": reason,
            },
        )
    )
