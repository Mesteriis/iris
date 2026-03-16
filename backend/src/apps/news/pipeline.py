import re
from dataclasses import dataclass
from typing import Any

from src.apps.market_data.domain import utc_now
from src.apps.news.constants import (
    NEWS_EVENT_ITEM_NORMALIZED,
    NEWS_EVENT_SYMBOL_CORRELATION_UPDATED,
    NEWS_NEGATIVE_KEYWORDS,
    NEWS_NORMALIZATION_STATUS_ERROR,
    NEWS_NORMALIZATION_STATUS_NORMALIZED,
    NEWS_POSITIVE_KEYWORDS,
    NEWS_TOPIC_KEYWORDS,
)
from src.apps.news.models import NewsItem, NewsItemLink
from src.apps.news.repositories import NewsItemLinkRepository, NewsItemRepository, NewsMarketDataRepository
from src.core.db.uow import BaseAsyncUnitOfWork
from src.runtime.streams.publisher import publish_event

_UPPERCASE_TOKEN_PATTERN = re.compile(r"\b[A-Z]{2,10}\b")
_QUOTE_SUFFIXES = ("USDT", "USDC", "USD", "EUR", "BTC", "ETH")


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _excerpt(text: str, limit: int = 200) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(limit - 3, 0)].rstrip() + "..."


def _clean_text(*parts: str | None) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _canonical_symbol(symbol: str) -> str:
    normalized = symbol.upper().split("_", 1)[0]
    for suffix in _QUOTE_SUFFIXES:
        if normalized.endswith(suffix) and len(normalized) > len(suffix) + 1:
            return normalized[: -len(suffix)]
    return normalized


def _symbol_aliases(symbol: str) -> set[str]:
    canonical = _canonical_symbol(symbol)
    raw = symbol.upper()
    primary = raw.split("_", 1)[0]
    aliases = {raw, primary, canonical}
    aliases.update(token for token in _UPPERCASE_TOKEN_PATTERN.findall(primary) if len(token) >= 2)
    return {alias for alias in aliases if alias}


def _sentiment_score(text: str) -> float:
    lowered = text.lower()
    positive = sum(lowered.count(token) for token in NEWS_POSITIVE_KEYWORDS)
    negative = sum(lowered.count(token) for token in NEWS_NEGATIVE_KEYWORDS)
    total = positive + negative
    if total <= 0:
        return 0.0
    return round(_clamp((positive - negative) / total, -1.0, 1.0), 4)


def _topic_matches(text: str) -> list[str]:
    lowered = text.lower()
    return sorted(
        topic
        for topic, keywords in NEWS_TOPIC_KEYWORDS.items()
        if any(keyword in lowered for keyword in keywords)
    )


def _sentiment_label(score: float) -> str:
    if score >= 0.2:
        return "positive"
    if score <= -0.2:
        return "negative"
    return "neutral"


@dataclass(frozen=True, slots=True)
class CoinAlias:
    coin_id: int
    coin_symbol: str
    coin_name: str
    canonical_symbol: str
    sort_order: int
    aliases: set[str]


def _quote_priority(symbol: str) -> int:
    primary = symbol.upper().split("_", 1)[0]
    for index, suffix in enumerate(_QUOTE_SUFFIXES):
        if primary.endswith(suffix):
            return index
    return len(_QUOTE_SUFFIXES)


class NewsNormalizationService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._items = NewsItemRepository(uow.session)
        self._market = NewsMarketDataRepository(uow.session)

    def _publish_after_commit(self, event_type: str, payload: dict[str, object]) -> None:
        def _publish() -> None:
            publish_event(event_type, dict(payload))

        self._uow.add_after_commit_action(_publish)

    async def normalize_item(self, *, item_id: int) -> dict[str, object]:
        item = await self._items.get_for_update(item_id)
        if item is None:
            return {"status": "skipped", "reason": "item_not_found", "item_id": int(item_id)}

        try:
            text = _clean_text(item.title, item.content_text, item.channel_name)
            aliases = await self._load_coin_aliases()
            uppercase_tokens = set(_UPPERCASE_TOKEN_PATTERN.findall(text))
            direct_symbols = {token.upper() for token in item.symbol_hints}
            matched_names: list[str] = []

            for alias in aliases:
                if alias.coin_name.lower() in text.lower():
                    matched_names.append(alias.coin_name)
                    direct_symbols.add(_canonical_symbol(alias.coin_symbol))
                if alias.aliases & uppercase_tokens:
                    direct_symbols.add(_canonical_symbol(alias.coin_symbol))

            topics = _topic_matches(text)
            sentiment = _sentiment_score(text)
            relevance = _clamp(
                0.15
                + (0.25 if direct_symbols else 0.0)
                + min(len(direct_symbols), 3) * 0.12
                + min(len(topics), 2) * 0.08
                + (0.08 if item.url else 0.0)
                + (0.05 if len(text) >= 80 else 0.0),
                0.0,
                0.99,
            )
            payload = {
                "detected_symbols": sorted(direct_symbols),
                "matched_names": sorted(set(matched_names)),
                "topics": topics,
                "sentiment_label": _sentiment_label(sentiment),
                "text_excerpt": _excerpt(text),
            }

            item.normalization_status = NEWS_NORMALIZATION_STATUS_NORMALIZED
            item.normalized_payload_json = payload
            item.normalized_at = utc_now()
            item.sentiment_score = round(sentiment, 4)
            item.relevance_score = round(relevance, 4)
        except Exception as exc:
            item.normalization_status = NEWS_NORMALIZATION_STATUS_ERROR
            item.normalized_payload_json = {"error": str(exc)[:255]}
            item.normalized_at = utc_now()
            return {
                "status": "error",
                "reason": "normalization_failed",
                "item_id": int(item_id),
                "error": str(exc)[:255],
            }

        self._publish_after_commit(
            NEWS_EVENT_ITEM_NORMALIZED,
            {
                "coin_id": 0,
                "timeframe": 0,
                "timestamp": item.published_at,
                "item_id": int(item.id),
                "source_id": int(item.source_id),
                "plugin_name": item.plugin_name,
                "detected_symbols": list(item.normalized_payload_json.get("detected_symbols", [])),
                "sentiment_score": item.sentiment_score,
                "relevance_score": item.relevance_score,
            },
        )
        return {
            "status": "ok",
            "item_id": int(item.id),
            "detected_symbols": list(item.normalized_payload_json.get("detected_symbols", [])),
            "sentiment_score": item.sentiment_score,
            "relevance_score": item.relevance_score,
        }

    async def _load_coin_aliases(self) -> list[CoinAlias]:
        rows = await self._market.list_coin_aliases()
        return [
            CoinAlias(
                coin_id=int(row.coin_id),
                coin_symbol=str(row.coin_symbol),
                coin_name=str(row.coin_name),
                canonical_symbol=_canonical_symbol(str(row.coin_symbol)),
                sort_order=int(row.sort_order),
                aliases=_symbol_aliases(str(row.coin_symbol)),
            )
            for row in rows
        ]


class NewsCorrelationService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._items = NewsItemRepository(uow.session)
        self._links = NewsItemLinkRepository(uow.session)

    def _publish_after_commit(self, event_type: str, payload: dict[str, object]) -> None:
        def _publish() -> None:
            publish_event(event_type, dict(payload))

        self._uow.add_after_commit_action(_publish)

    async def correlate_item(self, *, item_id: int) -> dict[str, object]:
        item = await self._items.get_for_update(item_id)
        if item is None:
            return {"status": "skipped", "reason": "item_not_found", "item_id": int(item_id)}

        detected_symbols = {
            str(symbol).upper()
            for symbol in (
                list(item.symbol_hints)
                + list((item.normalized_payload_json or {}).get("detected_symbols", []))
            )
        }
        aliases = await NewsNormalizationService(self._uow)._load_coin_aliases()
        lowered_text = _clean_text(item.title, item.content_text, item.channel_name).lower()
        await self._links.delete_by_item_id(int(item.id))

        created = 0
        winners: dict[str, tuple[tuple[int, int, int], CoinAlias, str, str, float]] = {}
        for alias in aliases:
            confidence = 0.0
            matched_symbol = None
            link_type = "symbol"
            for candidate in detected_symbols:
                if candidate in alias.aliases:
                    confidence = max(confidence, 0.72)
                    matched_symbol = candidate
                    link_type = "cashtag" if candidate in {hint.upper() for hint in item.symbol_hints} else "symbol"
            if alias.coin_name.lower() in lowered_text:
                confidence = max(confidence, 0.62)
                matched_symbol = matched_symbol or _canonical_symbol(alias.coin_symbol)
                link_type = "name"
            if confidence <= 0.0:
                continue
            confidence = round(
                _clamp(
                    confidence
                    + float(item.relevance_score or 0.0) * 0.2
                    + abs(float(item.sentiment_score or 0.0)) * 0.05,
                    0.0,
                    0.99,
                ),
                4,
            )
            if confidence < 0.55:
                continue
            rank = (_quote_priority(alias.coin_symbol), int(alias.sort_order), -int(alias.coin_id))
            current = winners.get(alias.canonical_symbol)
            if current is None or rank < current[0] or (rank == current[0] and confidence > current[4]):
                winners[alias.canonical_symbol] = (
                    rank,
                    alias,
                    str(matched_symbol or alias.canonical_symbol),
                    link_type,
                    confidence,
                )

        created_links: list[NewsItemLink] = []
        for _rank, alias, matched_symbol, link_type, confidence in winners.values():
            created_links.append(
                NewsItemLink(
                    news_item_id=int(item.id),
                    coin_id=alias.coin_id,
                    coin_symbol=alias.coin_symbol,
                    matched_symbol=matched_symbol,
                    link_type=link_type,
                    confidence=confidence,
                )
            )
            created += 1

        await self._links.add_many(created_links)
        links = sorted(created_links, key=lambda current: (-float(current.confidence), int(current.coin_id)))
        for link in links:
            self._publish_after_commit(
                NEWS_EVENT_SYMBOL_CORRELATION_UPDATED,
                {
                    "coin_id": int(link.coin_id),
                    "timeframe": 0,
                    "timestamp": item.published_at,
                    "item_id": int(item.id),
                    "source_id": int(item.source_id),
                    "plugin_name": item.plugin_name,
                    "coin_symbol": link.coin_symbol,
                    "matched_symbol": link.matched_symbol,
                    "link_type": link.link_type,
                    "confidence": link.confidence,
                    "relevance_score": item.relevance_score,
                    "sentiment_score": item.sentiment_score,
                },
            )

        return {
            "status": "ok",
            "item_id": int(item.id),
            "links_created": created,
            "coin_ids": [int(link.coin_id) for link in links],
        }


__all__ = ["NewsCorrelationService", "NewsNormalizationService"]
