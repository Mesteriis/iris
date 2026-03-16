from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from iris.apps.market_structure.constants import (
    MARKET_STRUCTURE_MANUAL_PROVIDER_COINALYZE,
    MARKET_STRUCTURE_MANUAL_PROVIDER_COINGLASS,
    MARKET_STRUCTURE_MANUAL_PROVIDER_DERIVATIVES_WEBHOOK,
    MARKET_STRUCTURE_MANUAL_PROVIDER_HYBLOCK,
    MARKET_STRUCTURE_MANUAL_PROVIDER_LIQSCOPE,
    MARKET_STRUCTURE_MANUAL_PROVIDER_LIQUIDATION_WEBHOOK,
)
from iris.apps.market_structure.exceptions import InvalidMarketStructureWebhookPayloadError
from iris.apps.market_structure.schemas import ManualMarketStructureIngestRequest, MarketStructureSnapshotCreate


@dataclass(frozen=True, slots=True)
class MarketStructureWebhookNormalizerDescriptor:
    provider: str
    display_name: str
    sample_payload: dict[str, Any]


class MarketStructureWebhookPayloadNormalizer(ABC):
    descriptor: MarketStructureWebhookNormalizerDescriptor

    def __init__(self, *, venue: str) -> None:
        self._venue = venue.strip().lower()

    def normalize_payload(self, payload: dict[str, Any]) -> ManualMarketStructureIngestRequest:
        if not isinstance(payload, dict):
            raise InvalidMarketStructureWebhookPayloadError("Webhook payload must be a JSON object.")
        items = self._extract_items(payload)
        if not items:
            raise InvalidMarketStructureWebhookPayloadError("Webhook payload did not contain any snapshots.")
        return ManualMarketStructureIngestRequest(snapshots=[self._build_snapshot(item) for item in items])

    @abstractmethod
    def _build_snapshot(self, item: dict[str, Any]) -> MarketStructureSnapshotCreate:
        raise NotImplementedError

    def _extract_items(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("items", "snapshots", "data", "events"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]

    def _mapping_section(self, value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        return {str(key): item for key, item in value.items()}

    def _merge_item_sections(self, item: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        metrics = self._mapping_section(item.get("metrics"))
        market = self._mapping_section(item.get("market"))
        liquidations = self._mapping_section(item.get("liquidations"))
        return metrics, market, liquidations

    def _first_present(self, mappings: tuple[dict[str, Any], ...], *keys: str) -> Any:
        for mapping in mappings:
            for key in keys:
                if key in mapping and mapping[key] not in (None, ""):
                    return mapping[key]
        return None

    def _build_model(self, item: dict[str, Any], *, timestamp: Any, values: dict[str, Any]) -> MarketStructureSnapshotCreate:
        if timestamp in (None, ""):
            raise InvalidMarketStructureWebhookPayloadError("Webhook payload is missing a timestamp.")
        payload_json = dict(item)
        payload_json.setdefault("normalized_by", self.descriptor.provider)
        values.setdefault("venue", self._venue)
        values.setdefault("payload_json", payload_json)
        values["timestamp"] = timestamp
        return MarketStructureSnapshotCreate.model_validate(values)


class LiqscopeWebhookNormalizer(MarketStructureWebhookPayloadNormalizer):
    descriptor = MarketStructureWebhookNormalizerDescriptor(
        provider=MARKET_STRUCTURE_MANUAL_PROVIDER_LIQSCOPE,
        display_name="Liqscope Webhook",
        sample_payload={
            "timestamp": "2026-03-12T12:00:00+00:00",
            "price": 3150.0,
            "open_interest": 21000.0,
            "funding_rate": 0.0009,
            "liquidations": {"long": 3300.0, "short": 120.0},
        },
    )

    def _build_snapshot(self, item: dict[str, Any]) -> MarketStructureSnapshotCreate:
        metrics, market, liquidations = self._merge_item_sections(item)
        timestamp = self._first_present((item, metrics), "timestamp", "ts", "event_time")
        values = {
            "last_price": self._first_present((item, metrics, market), "last_price", "price"),
            "mark_price": self._first_present((item, metrics, market), "mark_price", "mark"),
            "index_price": self._first_present((item, metrics, market), "index_price", "index"),
            "funding_rate": self._first_present((item, metrics, market), "funding_rate", "funding"),
            "open_interest": self._first_present((item, metrics, market), "open_interest", "oi"),
            "basis": self._first_present((item, metrics, market), "basis"),
            "volume": self._first_present((item, metrics, market), "volume", "volume_24h"),
            "liquidations_long": self._first_present((item, liquidations), "liquidations_long", "long", "longs"),
            "liquidations_short": self._first_present((item, liquidations), "liquidations_short", "short", "shorts"),
        }
        return self._build_model(item, timestamp=timestamp, values=values)


class LiquidationWebhookNormalizer(MarketStructureWebhookPayloadNormalizer):
    descriptor = MarketStructureWebhookNormalizerDescriptor(
        provider=MARKET_STRUCTURE_MANUAL_PROVIDER_LIQUIDATION_WEBHOOK,
        display_name="Liquidation Collector Webhook",
        sample_payload={
            "event_time": "2026-03-12T12:01:00+00:00",
            "metrics": {
                "last_price": 3151.0,
                "open_interest": 20800.0,
                "liquidations_long": 4100.0,
                "liquidations_short": 135.0,
            },
        },
    )

    def _build_snapshot(self, item: dict[str, Any]) -> MarketStructureSnapshotCreate:
        metrics, market, liquidations = self._merge_item_sections(item)
        timestamp = self._first_present((item, metrics), "event_time", "timestamp", "ts")
        values = {
            "last_price": self._first_present((metrics, item, market), "last_price", "price"),
            "mark_price": self._first_present((metrics, item, market), "mark_price"),
            "index_price": self._first_present((metrics, item, market), "index_price"),
            "funding_rate": self._first_present((metrics, item, market), "funding_rate"),
            "open_interest": self._first_present((metrics, item, market), "open_interest", "oi"),
            "basis": self._first_present((metrics, item, market), "basis"),
            "volume": self._first_present((metrics, item, market), "volume"),
            "liquidations_long": self._first_present((metrics, liquidations, item), "liquidations_long", "long", "longs"),
            "liquidations_short": self._first_present((metrics, liquidations, item), "liquidations_short", "short", "shorts"),
        }
        return self._build_model(item, timestamp=timestamp, values=values)


class DerivativesWebhookNormalizer(MarketStructureWebhookPayloadNormalizer):
    descriptor = MarketStructureWebhookNormalizerDescriptor(
        provider=MARKET_STRUCTURE_MANUAL_PROVIDER_DERIVATIVES_WEBHOOK,
        display_name="Derivatives Snapshot Webhook",
        sample_payload={
            "timestamp": "2026-03-12T12:02:00+00:00",
            "mark_price": 3152.0,
            "index_price": 3148.0,
            "funding_rate": 0.0008,
            "open_interest": 20500.0,
            "basis": 0.0012,
            "volume": 1205000.0,
            "liquidations": {"long": 900.0, "short": 40.0},
        },
    )

    def _build_snapshot(self, item: dict[str, Any]) -> MarketStructureSnapshotCreate:
        metrics, market, liquidations = self._merge_item_sections(item)
        timestamp = self._first_present((item, metrics), "timestamp", "event_time", "ts")
        values = {
            "last_price": self._first_present((item, metrics, market), "last_price", "price"),
            "mark_price": self._first_present((item, metrics, market), "mark_price", "mark"),
            "index_price": self._first_present((item, metrics, market), "index_price", "index"),
            "funding_rate": self._first_present((item, metrics, market), "funding_rate", "funding"),
            "open_interest": self._first_present((item, metrics, market), "open_interest", "oi"),
            "basis": self._first_present((item, metrics, market), "basis"),
            "volume": self._first_present((item, metrics, market), "volume", "volume_24h"),
            "liquidations_long": self._first_present((item, liquidations), "liquidations_long", "long", "longs"),
            "liquidations_short": self._first_present((item, liquidations), "liquidations_short", "short", "shorts"),
        }
        return self._build_model(item, timestamp=timestamp, values=values)


class CoinglassWebhookNormalizer(MarketStructureWebhookPayloadNormalizer):
    descriptor = MarketStructureWebhookNormalizerDescriptor(
        provider=MARKET_STRUCTURE_MANUAL_PROVIDER_COINGLASS,
        display_name="Coinglass Collector Webhook",
        sample_payload={
            "data": [
                {
                    "time": "2026-03-12T12:04:00+00:00",
                    "price": 3154.0,
                    "oi": 20700.0,
                    "funding": 0.0007,
                    "volume24h": 1100000.0,
                    "longLiquidationUsd": 5100.0,
                    "shortLiquidationUsd": 180.0,
                }
            ]
        },
    )

    def _build_snapshot(self, item: dict[str, Any]) -> MarketStructureSnapshotCreate:
        metrics, market, liquidations = self._merge_item_sections(item)
        timestamp = self._first_present((item, metrics), "time", "timestamp", "ts")
        values = {
            "last_price": self._first_present((item, metrics, market), "price", "last_price"),
            "mark_price": self._first_present((item, metrics, market), "markPrice", "mark_price"),
            "index_price": self._first_present((item, metrics, market), "indexPrice", "index_price"),
            "funding_rate": self._first_present((item, metrics, market), "funding", "fundingRate", "funding_rate"),
            "open_interest": self._first_present((item, metrics, market), "oi", "openInterest", "open_interest"),
            "basis": self._first_present((item, metrics, market), "basis", "basisRate"),
            "volume": self._first_present((item, metrics, market), "volume24h", "volume"),
            "liquidations_long": self._first_present(
                (item, metrics, liquidations), "longLiquidationUsd", "liquidations_long", "long", "longs"
            ),
            "liquidations_short": self._first_present(
                (item, metrics, liquidations), "shortLiquidationUsd", "liquidations_short", "short", "shorts"
            ),
        }
        return self._build_model(item, timestamp=timestamp, values=values)


class HyblockWebhookNormalizer(MarketStructureWebhookPayloadNormalizer):
    descriptor = MarketStructureWebhookNormalizerDescriptor(
        provider=MARKET_STRUCTURE_MANUAL_PROVIDER_HYBLOCK,
        display_name="Hyblock Collector Webhook",
        sample_payload={
            "events": [
                {
                    "ts": "2026-03-12T12:05:00+00:00",
                    "market": {
                        "last_price": 3155.0,
                        "mark_price": 3155.4,
                        "open_interest": 20650.0,
                        "funding_rate": 0.00072,
                    },
                    "liquidations": {"longs": 4700.0, "shorts": 220.0},
                }
            ]
        },
    )

    def _build_snapshot(self, item: dict[str, Any]) -> MarketStructureSnapshotCreate:
        metrics, market, liquidations = self._merge_item_sections(item)
        timestamp = self._first_present((item, market, metrics), "ts", "timestamp", "event_time")
        values = {
            "last_price": self._first_present((market, metrics, item), "last_price", "price"),
            "mark_price": self._first_present((market, metrics, item), "mark_price", "markPrice"),
            "index_price": self._first_present((market, metrics, item), "index_price", "indexPrice"),
            "funding_rate": self._first_present((market, metrics, item), "funding_rate", "funding"),
            "open_interest": self._first_present((market, metrics, item), "open_interest", "oi"),
            "basis": self._first_present((market, metrics, item), "basis"),
            "volume": self._first_present((market, metrics, item), "volume", "volume_24h"),
            "liquidations_long": self._first_present((liquidations, metrics, item), "longs", "long", "liquidations_long"),
            "liquidations_short": self._first_present((liquidations, metrics, item), "shorts", "short", "liquidations_short"),
        }
        return self._build_model(item, timestamp=timestamp, values=values)


class CoinalyzeWebhookNormalizer(MarketStructureWebhookPayloadNormalizer):
    descriptor = MarketStructureWebhookNormalizerDescriptor(
        provider=MARKET_STRUCTURE_MANUAL_PROVIDER_COINALYZE,
        display_name="Coinalyze Collector Webhook",
        sample_payload={
            "updateTime": "2026-03-12T12:06:00+00:00",
            "price": {"last": 3156.0, "mark": 3156.2, "index": 3152.1},
            "openInterest": 20620.0,
            "fundingRate": 0.00074,
            "basisPct": 0.0013,
            "liquidation": {"long": 1600.0, "short": 80.0},
            "volume": 990000.0,
        },
    )

    def _build_snapshot(self, item: dict[str, Any]) -> MarketStructureSnapshotCreate:
        metrics, market, liquidations = self._merge_item_sections(item)
        price = self._mapping_section(item.get("price"))
        liquidation = self._mapping_section(item.get("liquidation"))
        timestamp = self._first_present((item, metrics), "updateTime", "timestamp", "ts", "event_time")
        values = {
            "last_price": self._first_present((price, market, metrics, item), "last", "last_price", "price"),
            "mark_price": self._first_present((price, market, metrics, item), "mark", "mark_price"),
            "index_price": self._first_present((price, market, metrics, item), "index", "index_price"),
            "funding_rate": self._first_present((item, metrics, market), "fundingRate", "funding_rate", "funding"),
            "open_interest": self._first_present((item, metrics, market), "openInterest", "open_interest", "oi"),
            "basis": self._first_present((item, metrics, market), "basisPct", "basis", "basisRate"),
            "volume": self._first_present((item, metrics, market), "volume", "volume24h"),
            "liquidations_long": self._first_present((liquidation, liquidations, item), "long", "longs", "liquidations_long"),
            "liquidations_short": self._first_present((liquidation, liquidations, item), "short", "shorts", "liquidations_short"),
        }
        return self._build_model(item, timestamp=timestamp, values=values)


_REGISTRY: dict[str, type[MarketStructureWebhookPayloadNormalizer]] = {
    MARKET_STRUCTURE_MANUAL_PROVIDER_COINALYZE: CoinalyzeWebhookNormalizer,
    MARKET_STRUCTURE_MANUAL_PROVIDER_COINGLASS: CoinglassWebhookNormalizer,
    MARKET_STRUCTURE_MANUAL_PROVIDER_LIQSCOPE: LiqscopeWebhookNormalizer,
    MARKET_STRUCTURE_MANUAL_PROVIDER_LIQUIDATION_WEBHOOK: LiquidationWebhookNormalizer,
    MARKET_STRUCTURE_MANUAL_PROVIDER_HYBLOCK: HyblockWebhookNormalizer,
    MARKET_STRUCTURE_MANUAL_PROVIDER_DERIVATIVES_WEBHOOK: DerivativesWebhookNormalizer,
}


def get_market_structure_webhook_normalizer_class(
    provider: str,
) -> type[MarketStructureWebhookPayloadNormalizer] | None:
    return _REGISTRY.get(provider.strip().lower())


def create_market_structure_webhook_normalizer(
    *,
    provider: str,
    venue: str,
) -> MarketStructureWebhookPayloadNormalizer:
    normalizer_cls = get_market_structure_webhook_normalizer_class(provider)
    if normalizer_cls is None:
        raise InvalidMarketStructureWebhookPayloadError(f"Unsupported webhook payload provider '{provider}'.")
    return normalizer_cls(venue=venue)


__all__ = [
    "MarketStructureWebhookNormalizerDescriptor",
    "MarketStructureWebhookPayloadNormalizer",
    "create_market_structure_webhook_normalizer",
    "get_market_structure_webhook_normalizer_class",
]
