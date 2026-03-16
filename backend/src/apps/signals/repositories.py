from collections import defaultdict
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.cross_market.models import CoinRelation, SectorMetric
from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.domain import utc_now
from src.apps.market_data.models import Coin
from src.apps.news.constants import NEWS_NORMALIZATION_STATUS_NORMALIZED
from src.apps.news.models import NewsItem, NewsItemLink
from src.apps.patterns.models import PatternStatistic
from src.apps.signals.models import MarketDecision, Signal, SignalHistory
from src.core.db.persistence import AsyncRepository


class SignalHistoryRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="signals", repository_name="SignalHistoryRepository")

    async def list_signals_for_history(
        self,
        *,
        lookback_days: int,
        coin_id: int | None = None,
        timeframe: int | None = None,
        limit_per_scope: int | None = None,
    ) -> list[Signal]:
        self._log_debug(
            "repo.list_signal_history_signals",
            mode="read",
            lookback_days=lookback_days,
            coin_id=coin_id,
            timeframe=timeframe,
            limit_per_scope=limit_per_scope,
        )
        cutoff = utc_now() - timedelta(days=int(lookback_days))
        stmt = (
            select(Signal)
            .where(Signal.candle_timestamp >= cutoff)
            .order_by(Signal.coin_id.asc(), Signal.timeframe.asc(), Signal.candle_timestamp.asc(), Signal.created_at.asc())
        )
        if coin_id is not None:
            stmt = stmt.where(Signal.coin_id == int(coin_id))
        if timeframe is not None:
            stmt = stmt.where(Signal.timeframe == int(timeframe))
        rows = (await self.session.execute(stmt)).scalars().all()
        items = list(rows)
        if limit_per_scope is None:
            self._log_debug("repo.list_signal_history_signals.result", mode="read", count=len(items))
            return items

        grouped: dict[tuple[int, int], list[Signal]] = defaultdict(list)
        for row in items:
            grouped[(int(row.coin_id), int(row.timeframe))].append(row)
        limited: list[Signal] = []
        for scoped_rows in grouped.values():
            limited.extend(scoped_rows[-int(limit_per_scope) :])
        limited.sort(key=lambda row: (row.coin_id, row.timeframe, row.candle_timestamp, row.created_at))
        self._log_debug("repo.list_signal_history_signals.result", mode="read", count=len(limited))
        return limited

    async def upsert_signal_history(self, *, rows: Sequence[dict[str, object]]) -> int:
        self._log_info(
            "repo.upsert_signal_history_rows",
            mode="write",
            row_count=len(rows),
            bulk=True,
        )
        if not rows:
            return 0
        stmt = insert(SignalHistory).values(list(rows))
        stmt = stmt.on_conflict_do_update(
            index_elements=["coin_id", "timeframe", "signal_type", "candle_timestamp"],
            set_={
                "confidence": stmt.excluded.confidence,
                "market_regime": stmt.excluded.market_regime,
                "profit_after_24h": stmt.excluded.profit_after_24h,
                "profit_after_72h": stmt.excluded.profit_after_72h,
                "maximum_drawdown": stmt.excluded.maximum_drawdown,
                "result_return": stmt.excluded.result_return,
                "result_drawdown": stmt.excluded.result_drawdown,
                "evaluated_at": stmt.excluded.evaluated_at,
            },
        )
        await self.session.execute(stmt)
        await self.session.flush()
        count = len(rows)
        self._log_debug("repo.upsert_signal_history_rows.result", mode="write", count=count, bulk=True)
        return count


class SignalFusionRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="signals", repository_name="SignalFusionRepository")

    async def list_recent_signals(
        self,
        *,
        coin_id: int,
        timeframe: int,
        limit: int,
    ) -> list[Signal]:
        self._log_debug(
            "repo.list_recent_fusion_signals",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
            limit=limit,
        )
        rows = (
            await self.session.execute(
                select(Signal)
                .where(Signal.coin_id == int(coin_id), Signal.timeframe == int(timeframe))
                .order_by(Signal.candle_timestamp.desc(), Signal.created_at.desc(), Signal.id.desc())
                .limit(max(limit, 1))
            )
        ).scalars().all()
        items = list(rows)
        self._log_debug("repo.list_recent_fusion_signals.result", mode="read", count=len(items))
        return items

    async def get_coin_metrics(self, *, coin_id: int) -> CoinMetrics | None:
        self._log_debug("repo.get_signal_fusion_coin_metrics", mode="read", coin_id=coin_id)
        item = await self.session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(coin_id)).limit(1))
        self._log_debug("repo.get_signal_fusion_coin_metrics.result", mode="read", found=item is not None)
        return item

    async def get_latest_market_decision(self, *, coin_id: int, timeframe: int) -> MarketDecision | None:
        self._log_debug(
            "repo.get_latest_signal_market_decision",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
        )
        item = await self.session.scalar(
            select(MarketDecision)
            .where(MarketDecision.coin_id == int(coin_id), MarketDecision.timeframe == int(timeframe))
            .order_by(MarketDecision.created_at.desc(), MarketDecision.id.desc())
            .limit(1)
        )
        self._log_debug("repo.get_latest_signal_market_decision.result", mode="read", found=item is not None)
        return item

    async def add_market_decision(self, item: MarketDecision) -> MarketDecision:
        self._log_info(
            "repo.add_signal_market_decision",
            mode="write",
            coin_id=int(item.coin_id),
            timeframe=int(item.timeframe),
            decision=item.decision,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def list_candidate_fusion_timeframes(self, *, coin_id: int, allowed_timeframes: Sequence[int]) -> list[int]:
        self._log_debug(
            "repo.list_candidate_fusion_timeframes",
            mode="read",
            coin_id=coin_id,
            timeframes=list(allowed_timeframes),
        )
        rows = (
            await self.session.execute(
                select(Signal.timeframe)
                .where(Signal.coin_id == int(coin_id), Signal.timeframe.in_(tuple(int(item) for item in allowed_timeframes)))
                .distinct()
            )
        ).scalars().all()
        available = {int(row) for row in rows if int(row) > 0}
        items = [int(timeframe) for timeframe in allowed_timeframes if int(timeframe) in available]
        self._log_debug("repo.list_candidate_fusion_timeframes.result", mode="read", count=len(items))
        return items

    async def list_recent_news_rows(
        self,
        *,
        coin_id: int,
        reference_timestamp: object,
        since: object,
        limit: int,
    ) -> Sequence[Any]:
        self._log_debug(
            "repo.list_recent_signal_news_rows",
            mode="read",
            coin_id=coin_id,
            limit=limit,
            loading_profile="projection",
        )
        rows = (
            await self.session.execute(
                select(
                    NewsItem.id,
                    NewsItem.published_at,
                    NewsItem.sentiment_score,
                    NewsItem.relevance_score,
                    NewsItemLink.confidence,
                )
                .join(NewsItemLink, NewsItemLink.news_item_id == NewsItem.id)
                .where(
                    NewsItemLink.coin_id == int(coin_id),
                    NewsItem.normalization_status == NEWS_NORMALIZATION_STATUS_NORMALIZED,
                    NewsItem.published_at >= since,
                    NewsItem.published_at <= reference_timestamp,
                )
                .order_by(NewsItem.published_at.desc(), NewsItemLink.confidence.desc())
                .limit(max(limit, 1))
            )
        ).all()
        self._log_debug("repo.list_recent_signal_news_rows.result", mode="read", count=len(rows))
        return rows

    async def list_pattern_success_rates(
        self,
        *,
        timeframe: int,
        pattern_slugs: Sequence[str],
        market_regimes: Sequence[str],
    ) -> dict[tuple[str, str], float]:
        self._log_debug(
            "repo.list_signal_pattern_success_rates",
            mode="read",
            timeframe=timeframe,
            pattern_count=len(pattern_slugs),
            regime_count=len(market_regimes),
        )
        if not pattern_slugs:
            return {}
        rows = (
            await self.session.execute(
                select(PatternStatistic.pattern_slug, PatternStatistic.market_regime, PatternStatistic.success_rate).where(
                    PatternStatistic.pattern_slug.in_(tuple(pattern_slugs)),
                    PatternStatistic.timeframe == int(timeframe),
                    PatternStatistic.market_regime.in_(tuple(market_regimes)),
                )
            )
        ).all()
        items = {(str(row.pattern_slug), str(row.market_regime)): float(row.success_rate) for row in rows}
        self._log_debug("repo.list_signal_pattern_success_rates.result", mode="read", count=len(items))
        return items

    async def list_alignment_relations(self, *, follower_coin_id: int, limit: int = 3) -> list[CoinRelation]:
        self._log_debug(
            "repo.list_signal_alignment_relations",
            mode="read",
            follower_coin_id=follower_coin_id,
            limit=limit,
        )
        rows = (
            await self.session.execute(
                select(CoinRelation)
                .where(CoinRelation.follower_coin_id == int(follower_coin_id), CoinRelation.confidence >= 0.45)
                .order_by(CoinRelation.confidence.desc(), CoinRelation.correlation.desc())
                .limit(max(limit, 1))
            )
        ).scalars().all()
        items = list(rows)
        self._log_debug("repo.list_signal_alignment_relations.result", mode="read", count=len(items))
        return items

    async def list_latest_leader_decisions(
        self,
        *,
        leader_coin_ids: Sequence[int],
        timeframe: int,
    ) -> dict[int, tuple[str, float]]:
        self._log_debug(
            "repo.list_signal_leader_decisions",
            mode="read",
            timeframe=timeframe,
            leader_count=len(leader_coin_ids),
        )
        if not leader_coin_ids:
            return {}
        rows = (
            await self.session.execute(
                select(MarketDecision.coin_id, MarketDecision.decision, MarketDecision.confidence)
                .where(
                    MarketDecision.coin_id.in_(tuple(int(item) for item in leader_coin_ids)),
                    MarketDecision.timeframe == int(timeframe),
                )
                .order_by(MarketDecision.coin_id.asc(), MarketDecision.created_at.desc(), MarketDecision.id.desc())
            )
        ).all()
        items: dict[int, tuple[str, float]] = {}
        for row in rows:
            coin_id = int(row.coin_id)
            if coin_id not in items:
                items[coin_id] = (str(row.decision), float(row.confidence))
        self._log_debug("repo.list_signal_leader_decisions.result", mode="read", count=len(items))
        return items

    async def get_sector_trend(self, *, coin_id: int, timeframe: int) -> str | None:
        self._log_debug("repo.get_signal_sector_trend", mode="read", coin_id=coin_id, timeframe=timeframe)
        sector_id = await self.session.scalar(select(Coin.sector_id).where(Coin.id == int(coin_id)).limit(1))
        if sector_id is None:
            self._log_debug("repo.get_signal_sector_trend.result", mode="read", found=False)
            return None
        trend = await self.session.scalar(
            select(SectorMetric.trend).where(
                SectorMetric.sector_id == int(sector_id),
                SectorMetric.timeframe == int(timeframe),
            )
        )
        if trend is None and int(timeframe) != 60:
            trend = await self.session.scalar(
                select(SectorMetric.trend).where(
                    SectorMetric.sector_id == int(sector_id),
                    SectorMetric.timeframe == 60,
                )
            )
        self._log_debug("repo.get_signal_sector_trend.result", mode="read", found=trend is not None)
        return str(trend) if trend is not None else None


__all__ = ["SignalFusionRepository", "SignalHistoryRepository"]
