from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.apps.anomalies.constants import (
    BENCHMARK_SYMBOL_PREFIXES,
    MAX_RELATED_PEERS,
    MAX_SECTOR_PEERS,
    OPEN_ANOMALY_STATUSES,
    PORTFOLIO_OPEN_POSITION_STATUS,
)
from app.apps.anomalies.models import MarketAnomaly, MarketStructureSnapshot
from app.apps.anomalies.schemas import AnomalyDetectionContext, AnomalyDraft, BenchmarkSeries, MarketStructurePoint
from app.apps.cross_market.models import CoinRelation, Sector
from app.apps.indicators.models import CoinMetrics
from app.apps.market_data.domain import ensure_utc
from app.apps.market_data.models import Candle, Coin
from app.apps.market_data.repos import CandlePoint
from app.apps.portfolio.models import PortfolioPosition


class AnomalyRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _load_candles(self, coin_id: int, timeframe: int, limit: int) -> list[CandlePoint]:
        rows = (
            await self._session.execute(
                select(Candle.timestamp, Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume)
                .where(Candle.coin_id == coin_id, Candle.timeframe == timeframe)
                .order_by(Candle.timestamp.desc())
                .limit(max(limit, 1))
            )
        ).all()
        return [
            CandlePoint(
                timestamp=ensure_utc(row.timestamp),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume) if row.volume is not None else None,
            )
            for row in reversed(rows)
        ]

    async def _load_market_structure_snapshots(
        self,
        *,
        coin_id: int,
        timeframe: int,
        timestamp: datetime,
        lookback: int,
    ) -> dict[str, list[MarketStructurePoint]]:
        rows = (
            await self._session.execute(
                select(MarketStructureSnapshot)
                .where(
                    MarketStructureSnapshot.coin_id == coin_id,
                    MarketStructureSnapshot.timeframe == timeframe,
                    MarketStructureSnapshot.timestamp <= ensure_utc(timestamp),
                )
                .order_by(MarketStructureSnapshot.timestamp.desc())
                .limit(max(int(lookback) * 12, 96))
            )
        ).scalars().all()
        grouped: dict[str, list[MarketStructurePoint]] = defaultdict(list)
        for row in reversed(rows):
            grouped[str(row.venue)].append(
                MarketStructurePoint(
                    venue=str(row.venue),
                    timestamp=ensure_utc(row.timestamp),
                    last_price=float(row.last_price) if row.last_price is not None else None,
                    mark_price=float(row.mark_price) if row.mark_price is not None else None,
                    index_price=float(row.index_price) if row.index_price is not None else None,
                    funding_rate=float(row.funding_rate) if row.funding_rate is not None else None,
                    open_interest=float(row.open_interest) if row.open_interest is not None else None,
                    basis=float(row.basis) if row.basis is not None else None,
                    liquidations_long=float(row.liquidations_long) if row.liquidations_long is not None else None,
                    liquidations_short=float(row.liquidations_short) if row.liquidations_short is not None else None,
                    volume=float(row.volume) if row.volume is not None else None,
                    payload_json=dict(row.payload_json or {}),
                )
            )
        return {venue: points[-lookback:] for venue, points in grouped.items() if points}

    async def _has_open_portfolio_position(self, coin_id: int, timeframe: int) -> bool:
        count = await self._session.scalar(
            select(func.count())
            .select_from(PortfolioPosition)
            .where(
                PortfolioPosition.coin_id == coin_id,
                PortfolioPosition.timeframe == timeframe,
                PortfolioPosition.status == PORTFOLIO_OPEN_POSITION_STATUS,
            )
        )
        return bool(count)

    async def has_open_portfolio_position(self, coin_id: int, timeframe: int) -> bool:
        return await self._has_open_portfolio_position(coin_id, timeframe)

    async def _benchmark_coin(self, *, exclude_coin_id: int) -> tuple[int, str] | None:
        predicates = [Coin.symbol.like(f"{prefix}%") for prefix in BENCHMARK_SYMBOL_PREFIXES]
        rows = (
            await self._session.execute(
                select(Coin.id, Coin.symbol)
                .where(
                    Coin.deleted_at.is_(None),
                    Coin.enabled.is_(True),
                    Coin.id != exclude_coin_id,
                    or_(*predicates),
                )
                .order_by(Coin.symbol.asc())
                .limit(5)
            )
        ).all()
        if not rows:
            return None
        exact = next((row for row in rows if row.symbol in BENCHMARK_SYMBOL_PREFIXES), None)
        selected = exact or rows[0]
        return int(selected.id), str(selected.symbol)

    async def load_fast_detection_context(
        self,
        *,
        coin_id: int,
        timeframe: int,
        timestamp: datetime,
        lookback: int,
    ) -> AnomalyDetectionContext | None:
        row = (
            await self._session.execute(
                select(Coin, CoinMetrics.market_regime, Sector.name)
                .outerjoin(CoinMetrics, CoinMetrics.coin_id == Coin.id)
                .outerjoin(Sector, Sector.id == Coin.sector_id)
                .where(Coin.id == coin_id, Coin.deleted_at.is_(None), Coin.enabled.is_(True))
            )
        ).first()
        if row is None:
            return None
        coin, market_regime, sector_name = row
        candles = await self._load_candles(coin_id, timeframe, lookback)
        if not candles:
            return None

        benchmark: BenchmarkSeries | None = None
        benchmark_coin = await self._benchmark_coin(exclude_coin_id=coin_id)
        if benchmark_coin is not None:
            benchmark_id, benchmark_symbol = benchmark_coin
            benchmark_candles = await self._load_candles(benchmark_id, timeframe, lookback)
            if benchmark_candles:
                benchmark = BenchmarkSeries(symbol=benchmark_symbol, candles=benchmark_candles)

        return AnomalyDetectionContext(
            coin_id=int(coin.id),
            symbol=str(coin.symbol),
            timeframe=int(timeframe),
            timestamp=ensure_utc(timestamp),
            candles=candles,
            market_regime=str(market_regime) if market_regime is not None else None,
            sector=str(sector_name) if sector_name is not None else str(coin.sector_code or "") or None,
            portfolio_relevant=await self._has_open_portfolio_position(coin_id, timeframe),
            benchmark=benchmark,
        )

    async def _load_sector_peers(
        self,
        *,
        coin_id: int,
        sector_id: int | None,
        sector_code: str | None,
    ) -> list[tuple[int, str]]:
        stmt = (
            select(Coin.id, Coin.symbol)
            .where(
                Coin.deleted_at.is_(None),
                Coin.enabled.is_(True),
                Coin.id != coin_id,
            )
            .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
            .limit(MAX_SECTOR_PEERS)
        )
        if sector_id is not None:
            stmt = stmt.where(Coin.sector_id == sector_id)
        elif sector_code is not None:
            stmt = stmt.where(Coin.sector_code == sector_code)
        else:
            return []
        rows = (await self._session.execute(stmt)).all()
        return [(int(row.id), str(row.symbol)) for row in rows]

    async def _load_related_peers(self, *, coin_id: int) -> list[tuple[int, str]]:
        relation_rows = (
            await self._session.execute(
                select(
                    CoinRelation.leader_coin_id,
                    CoinRelation.follower_coin_id,
                    CoinRelation.confidence,
                )
                .where(
                    or_(
                        CoinRelation.leader_coin_id == coin_id,
                        CoinRelation.follower_coin_id == coin_id,
                    )
                )
                .order_by(CoinRelation.confidence.desc())
                .limit(MAX_RELATED_PEERS)
            )
        ).all()
        peer_ids = []
        for row in relation_rows:
            peer_id = int(row.follower_coin_id) if int(row.leader_coin_id) == coin_id else int(row.leader_coin_id)
            if peer_id not in peer_ids:
                peer_ids.append(peer_id)
        if not peer_ids:
            return []
        peer_rows = (
            await self._session.execute(
                select(Coin.id, Coin.symbol)
                .where(Coin.id.in_(peer_ids), Coin.deleted_at.is_(None), Coin.enabled.is_(True))
                .order_by(Coin.symbol.asc())
            )
        ).all()
        return [(int(row.id), str(row.symbol)) for row in peer_rows]

    async def load_sector_detection_context(
        self,
        *,
        coin_id: int,
        timeframe: int,
        timestamp: datetime,
        lookback: int,
    ) -> AnomalyDetectionContext | None:
        row = (
            await self._session.execute(
                select(Coin, CoinMetrics.market_regime)
                .outerjoin(CoinMetrics, CoinMetrics.coin_id == Coin.id)
                .where(Coin.id == coin_id, Coin.deleted_at.is_(None), Coin.enabled.is_(True))
            )
        ).first()
        if row is None:
            return None
        coin, market_regime = row
        context = await self.load_fast_detection_context(
            coin_id=coin_id,
            timeframe=timeframe,
            timestamp=timestamp,
            lookback=lookback,
        )
        if context is None:
            return None

        sector_peer_candles: dict[str, list[CandlePoint]] = {}
        for peer_id, symbol in await self._load_sector_peers(
            coin_id=coin_id,
            sector_id=int(coin.sector_id) if coin.sector_id is not None else None,
            sector_code=str(coin.sector_code) if coin.sector_code is not None else None,
        ):
            candles = await self._load_candles(peer_id, timeframe, lookback)
            if len(candles) >= 2:
                sector_peer_candles[symbol] = candles

        related_peer_candles: dict[str, list[CandlePoint]] = {}
        for peer_id, symbol in await self._load_related_peers(coin_id=coin_id):
            candles = await self._load_candles(peer_id, timeframe, lookback)
            if len(candles) >= 2:
                related_peer_candles[symbol] = candles

        context.market_regime = str(market_regime) if market_regime is not None else context.market_regime
        context.sector_peer_candles = sector_peer_candles
        context.related_peer_candles = related_peer_candles
        return context

    async def load_market_structure_detection_context(
        self,
        *,
        coin_id: int,
        timeframe: int,
        timestamp: datetime,
        lookback: int,
    ) -> AnomalyDetectionContext | None:
        context = await self.load_fast_detection_context(
            coin_id=coin_id,
            timeframe=timeframe,
            timestamp=timestamp,
            lookback=lookback,
        )
        if context is None:
            return None
        context.venue_snapshots = await self._load_market_structure_snapshots(
            coin_id=coin_id,
            timeframe=timeframe,
            timestamp=timestamp,
            lookback=lookback,
        )
        return context

    async def load_latest_open_anomaly(
        self,
        *,
        coin_id: int,
        timeframe: int,
        anomaly_type: str,
    ) -> MarketAnomaly | None:
        return (
            await self._session.execute(
                select(MarketAnomaly)
                .where(
                    MarketAnomaly.coin_id == coin_id,
                    MarketAnomaly.timeframe == timeframe,
                    MarketAnomaly.anomaly_type == anomaly_type,
                    MarketAnomaly.status.in_(OPEN_ANOMALY_STATUSES),
                )
                .order_by(MarketAnomaly.detected_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def create_anomaly(self, draft: AnomalyDraft) -> MarketAnomaly:
        anomaly = MarketAnomaly(
            coin_id=draft.coin_id,
            symbol=draft.symbol,
            timeframe=draft.timeframe,
            anomaly_type=draft.anomaly_type,
            severity=draft.severity,
            confidence=draft.confidence,
            score=draft.score,
            status=draft.status,
            detected_at=draft.detected_at,
            window_start=draft.window_start,
            window_end=draft.window_end,
            market_regime=draft.market_regime,
            sector=draft.sector,
            summary=draft.summary,
            payload_json=draft.payload_json,
            cooldown_until=draft.cooldown_until,
            last_confirmed_at=draft.detected_at,
        )
        self._session.add(anomaly)
        await self._session.flush()
        return anomaly

    async def touch_anomaly(
        self,
        anomaly: MarketAnomaly,
        *,
        status: str | None = None,
        score: float | None = None,
        confidence: float | None = None,
        summary: str | None = None,
        payload_json: dict[str, object] | None = None,
        cooldown_until: datetime | None = None,
        resolved_at: datetime | None = None,
        last_confirmed_at: datetime | None = None,
    ) -> MarketAnomaly:
        if status is not None:
            anomaly.status = status
        if score is not None:
            anomaly.score = score
        if confidence is not None:
            anomaly.confidence = confidence
        if summary is not None:
            anomaly.summary = summary
        if payload_json is not None:
            anomaly.payload_json = payload_json
        if cooldown_until is not None:
            anomaly.cooldown_until = cooldown_until
        if resolved_at is not None:
            anomaly.resolved_at = resolved_at
        if last_confirmed_at is not None:
            anomaly.last_confirmed_at = last_confirmed_at
        await self._session.flush()
        return anomaly

    async def get_anomaly(self, anomaly_id: int) -> MarketAnomaly | None:
        return await self._session.get(MarketAnomaly, anomaly_id)

    async def count_active_sector_anomalies(self, *, sector: str | None, timeframe: int) -> int:
        if not sector:
            return 0
        count = await self._session.scalar(
            select(func.count())
            .select_from(MarketAnomaly)
            .where(
                MarketAnomaly.sector == sector,
                MarketAnomaly.timeframe == timeframe,
                MarketAnomaly.status.in_(("new", "active")),
            )
        )
        return int(count or 0)

    async def list_active_anomalies(self, *, limit: int = 50) -> list[MarketAnomaly]:
        return (
            await self._session.execute(
                select(MarketAnomaly)
                .where(MarketAnomaly.status.in_(("new", "active")))
                .order_by(MarketAnomaly.detected_at.desc())
                .limit(limit)
            )
        ).scalars().all()

    async def anomalies_by_symbol(self, *, limit: int = 50) -> dict[str, list[MarketAnomaly]]:
        items = await self.list_active_anomalies(limit=limit)
        grouped: dict[str, list[MarketAnomaly]] = defaultdict(list)
        for item in items:
            grouped[item.symbol].append(item)
        return grouped
