from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from src.apps.cross_market.models import Sector, SectorMetric
from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.domain import ensure_utc, utc_now
from src.apps.market_data.models import Coin
from src.apps.patterns.domain.cycle import _detect_cycle_phase
from src.apps.patterns.domain.discovery import (
    DISCOVERY_HORIZON,
    DISCOVERY_STEP,
    DISCOVERY_WINDOW_BARS,
    _window_signature,
)
from src.apps.patterns.domain.regime import read_regime_details
from src.apps.patterns.domain.strategy import (
    HORIZON_BARS_BY_TIMEFRAME,
    MAX_DISCOVERED_STRATEGIES,
    MIN_DISCOVERY_SAMPLE,
    STRATEGY_LOOKBACK_DAYS,
    StrategyCandidate,
    StrategyObservation,
    _candidate_definitions,
    _context_from_window,
    _sharpe_ratio,
    _signal_outcome,
    _strategy_description,
    _strategy_enabled,
    _strategy_name,
)
from src.apps.patterns.models import MarketCycle
from src.apps.signals.models import Signal, Strategy, StrategyPerformance, StrategyRule


class PatternMarketDiscoveryMixin:
    async def _refresh_sector_metrics(self, *, timeframe: int | None = None) -> dict[str, object]:
        sectors = (await self.session.execute(select(Sector).order_by(Sector.name.asc()))).scalars().all()
        if not sectors:
            return {"status": "skipped", "reason": "sectors_not_found"}

        timeframes = [timeframe] if timeframe is not None else [15, 60, 240, 1440]
        coins = (
            (
                await self.session.execute(
                    select(Coin)
                    .where(Coin.enabled.is_(True), Coin.deleted_at.is_(None), Coin.sector_id.is_not(None))
                    .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
                )
            )
            .scalars()
            .all()
        )
        coins_by_sector: dict[int, list[Coin]] = defaultdict(list)
        for coin in coins:
            if coin.sector_id is not None:
                coins_by_sector[int(coin.sector_id)].append(coin)
        metrics_rows = (
            (
                await self.session.execute(
                    select(CoinMetrics).where(CoinMetrics.coin_id.in_([int(coin.id) for coin in coins]))
                    if coins
                    else select(CoinMetrics).where(False)
                )
            )
            .scalars()
            .all()
        )
        metrics_by_coin = {int(row.coin_id): row for row in metrics_rows}

        created = 0
        for current_timeframe in timeframes:
            market_returns: list[float] = []
            sector_rows: list[dict[str, object]] = []
            for sector in sectors:
                sector_coins = coins_by_sector.get(int(sector.id), [])
                if not sector_coins:
                    continue
                price_changes: list[float] = []
                volatility_values: list[float] = []
                capital_flow_components: list[float] = []
                for coin in sector_coins:
                    price_change, bar_volatility = await self._coin_bar_return(
                        coin_id=int(coin.id),
                        timeframe=current_timeframe,
                    )
                    metrics = metrics_by_coin.get(int(coin.id))
                    if price_change is not None:
                        price_changes.append(price_change)
                        market_returns.append(price_change)
                    if bar_volatility is not None:
                        volatility_values.append(bar_volatility)
                    if metrics is not None:
                        market_cap_component = ((metrics.market_cap or 0.0) / 1_000_000_000) * (price_change or 0.0)
                        volume_component = (metrics.volume_change_24h or 0.0) / 100
                        capital_flow_components.append(market_cap_component + volume_component)
                if not price_changes:
                    continue
                sector_rows.append(
                    {
                        "sector_id": int(sector.id),
                        "timeframe": current_timeframe,
                        "sector_strength": sum(price_changes) / len(price_changes),
                        "relative_strength": 0.0,
                        "capital_flow": sum(capital_flow_components) / len(capital_flow_components)
                        if capital_flow_components
                        else 0.0,
                        "volatility": sum(volatility_values) / len(volatility_values) if volatility_values else 0.0,
                        "updated_at": utc_now(),
                    }
                )
            market_return = sum(market_returns) / len(market_returns) if market_returns else 0.0
            for row in sector_rows:
                row["relative_strength"] = float(row["sector_strength"]) - market_return
            created += await self._replace_sector_metrics(timeframe=current_timeframe, rows=sector_rows)
        return {"status": "ok", "updated": created}

    async def _coin_bar_return(self, *, coin_id: int, timeframe: int) -> tuple[float | None, float | None]:
        candles = await self._fetch_candle_points(coin_id=coin_id, timeframe=timeframe, limit=25)
        if len(candles) < 2:
            return None, None
        previous = float(candles[-2].close)
        current = float(candles[-1].close)
        change = (current - previous) / previous if previous else 0.0
        closes = [float(item.close) for item in candles[-20:]]
        mean_close = sum(closes) / len(closes)
        volatility = (sum((value - mean_close) ** 2 for value in closes) / len(closes)) ** 0.5 if closes else 0.0
        return change, (volatility / current if current else 0.0)

    async def _refresh_market_cycles(self) -> dict[str, object]:
        coins = await self._coins.list(enabled_only=True)
        items = []
        for coin in coins:
            for timeframe in (15, 60, 240, 1440):
                metrics = await self.session.scalar(
                    select(CoinMetrics).where(CoinMetrics.coin_id == int(coin.id)).limit(1)
                )
                if metrics is None:
                    items.append({"status": "skipped", "reason": "coin_metrics_not_found", "coin_id": int(coin.id)})
                    continue
                pattern_density = int(
                    (
                        await self.session.execute(
                            select(func.count())
                            .select_from(Signal)
                            .where(
                                Signal.coin_id == int(coin.id),
                                Signal.timeframe == timeframe,
                                Signal.signal_type.like("pattern_%"),
                                ~Signal.signal_type.like("pattern_cluster_%"),
                                ~Signal.signal_type.like("pattern_hierarchy_%"),
                            )
                        )
                    ).scalar_one()
                    or 0
                )
                cluster_frequency = int(
                    (
                        await self.session.execute(
                            select(func.count())
                            .select_from(Signal)
                            .where(
                                Signal.coin_id == int(coin.id),
                                Signal.timeframe == timeframe,
                                Signal.signal_type.like("pattern_cluster_%"),
                            )
                        )
                    ).scalar_one()
                    or 0
                )
                sector_metric = (
                    await self.session.get(SectorMetric, (int(coin.sector_id), timeframe))
                    if coin.sector_id is not None
                    else None
                )
                regime_snapshot = read_regime_details(metrics.market_regime_details, timeframe)
                phase, confidence = _detect_cycle_phase(
                    trend_score=metrics.trend_score,
                    regime=regime_snapshot.regime if regime_snapshot is not None else metrics.market_regime,
                    volatility=metrics.volatility,
                    price_current=metrics.price_current,
                    pattern_density=pattern_density,
                    cluster_frequency=cluster_frequency,
                    sector_strength=sector_metric.sector_strength if sector_metric is not None else None,
                    capital_flow=sector_metric.capital_flow if sector_metric is not None else None,
                )
                stmt = insert(MarketCycle).values(
                    {
                        "coin_id": int(coin.id),
                        "timeframe": timeframe,
                        "cycle_phase": phase,
                        "confidence": confidence,
                        "detected_at": utc_now(),
                    }
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["coin_id", "timeframe"],
                    set_={
                        "cycle_phase": stmt.excluded.cycle_phase,
                        "confidence": stmt.excluded.confidence,
                        "detected_at": stmt.excluded.detected_at,
                    },
                )
                await self.session.execute(stmt)
                items.append(
                    {
                        "status": "ok",
                        "coin_id": int(coin.id),
                        "timeframe": timeframe,
                        "cycle_phase": phase,
                        "confidence": confidence,
                    }
                )
        await self._uow.flush()
        return {"status": "ok", "items": items, "cycles": len(items)}

    async def _refresh_discovered_patterns(self) -> dict[str, object]:
        if not await self._feature_enabled("pattern_discovery_engine"):
            return {"status": "skipped", "reason": "pattern_discovery_disabled"}

        aggregates: dict[tuple[str, int], list[tuple[float, float]]] = defaultdict(list)
        coins = await self._coins.list(enabled_only=True)
        for coin in coins:
            for candle_config in coin.candles_config or []:
                timeframe = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}.get(str(candle_config["interval"]))
                if timeframe is None:
                    continue
                candles = await self._fetch_candle_points(
                    coin_id=int(coin.id),
                    timeframe=timeframe,
                    limit=min(int(candle_config.get("retention_bars", 220)), 240),
                )
                if len(candles) < DISCOVERY_WINDOW_BARS + DISCOVERY_HORIZON:
                    continue
                closes = [float(item.close) for item in candles]
                lows = [float(item.low) for item in candles]
                for start_index in range(
                    0,
                    len(candles) - DISCOVERY_WINDOW_BARS - DISCOVERY_HORIZON + 1,
                    DISCOVERY_STEP,
                ):
                    window_closes = closes[start_index : start_index + DISCOVERY_WINDOW_BARS]
                    future_closes = closes[
                        start_index + DISCOVERY_WINDOW_BARS : start_index + DISCOVERY_WINDOW_BARS + DISCOVERY_HORIZON
                    ]
                    future_lows = lows[
                        start_index + DISCOVERY_WINDOW_BARS : start_index + DISCOVERY_WINDOW_BARS + DISCOVERY_HORIZON
                    ]
                    structure_hash = _window_signature(window_closes)
                    entry = window_closes[-1]
                    avg_return = (future_closes[-1] - entry) / max(entry, 1e-9)
                    avg_drawdown = (min(future_lows) - entry) / max(entry, 1e-9)
                    aggregates[(structure_hash, timeframe)].append((avg_return, avg_drawdown))

        rows: list[dict[str, object]] = []
        for (structure_hash, timeframe), outcomes in aggregates.items():
            sample_size = len(outcomes)
            if sample_size < 3:
                continue
            avg_return = sum(item[0] for item in outcomes) / sample_size
            avg_drawdown = sum(item[1] for item in outcomes) / sample_size
            confidence = max(min(0.5 + sample_size / 20 + avg_return - abs(avg_drawdown) * 0.5, 0.95), 0.1)
            rows.append(
                {
                    "structure_hash": structure_hash,
                    "timeframe": timeframe,
                    "sample_size": sample_size,
                    "avg_return": avg_return,
                    "avg_drawdown": avg_drawdown,
                    "confidence": confidence,
                }
            )

        await self._replace_discovered_patterns(rows=rows)
        return {"status": "ok", "patterns": len(rows)}

    async def _refresh_strategies(self) -> dict[str, object]:
        cutoff = utc_now() - timedelta(days=STRATEGY_LOOKBACK_DAYS)
        signals = (
            (
                await self.session.execute(
                    select(Signal)
                    .where(Signal.candle_timestamp >= cutoff, Signal.signal_type.like("pattern_%"))
                    .order_by(
                        Signal.coin_id.asc(),
                        Signal.timeframe.asc(),
                        Signal.candle_timestamp.asc(),
                        Signal.created_at.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        grouped: dict[tuple[int, int], dict[object, list[Signal]]] = defaultdict(lambda: defaultdict(list))
        for signal in signals:
            grouped[(int(signal.coin_id), int(signal.timeframe))][ensure_utc(signal.candle_timestamp)].append(signal)

        coin_rows = (
            (
                await self.session.execute(
                    select(Coin).options(selectinload(Coin.sector)).where(Coin.deleted_at.is_(None))
                )
            )
            .scalars()
            .all()
        )
        coin_map = {int(coin.id): coin for coin in coin_rows}
        observations_by_candidate: dict[StrategyCandidate, list[StrategyObservation]] = defaultdict(list)

        for (coin_id, timeframe), groups in grouped.items():
            if not groups:
                continue
            ordered_timestamps = sorted(groups)
            start = ordered_timestamps[0] - timedelta(minutes=timeframe * 220)
            end = ordered_timestamps[-1] + timedelta(
                minutes=timeframe * (HORIZON_BARS_BY_TIMEFRAME.get(timeframe, 8) + 1)
            )
            candles = await self._fetch_candle_points_between(
                coin_id=coin_id,
                timeframe=timeframe,
                window_start=start,
                window_end=end,
            )
            if len(candles) < 30:
                continue
            index_map = {ensure_utc(candle.timestamp): index for index, candle in enumerate(candles)}
            coin = coin_map.get(coin_id)
            sector = coin.sector.name if coin is not None and coin.sector is not None else "*"
            sector_metric = (
                await self.session.get(SectorMetric, (int(coin.sector_id), timeframe))
                if coin is not None and coin.sector_id is not None
                else None
            )
            for candle_timestamp in ordered_timestamps:
                signal_stack = groups[candle_timestamp]
                outcome = _signal_outcome(
                    signals=signal_stack,
                    candles=candles,
                    index_map=index_map,
                    timeframe=timeframe,
                    candle_timestamp=candle_timestamp,
                )
                if outcome is None:
                    continue
                open_timestamp = candle_timestamp - timedelta(minutes=timeframe)
                candle_index = index_map.get(open_timestamp)
                if candle_index is None:
                    continue
                window = candles[max(0, candle_index - 199) : candle_index + 1]
                if len(window) < 20:
                    continue
                regime, cycle = _context_from_window(window=window, signals=signal_stack, sector_metric=sector_metric)
                for candidate in _candidate_definitions(
                    timeframe=timeframe,
                    signals=signal_stack,
                    regime=regime,
                    sector=sector,
                    cycle=cycle,
                ):
                    observations_by_candidate[candidate].append(
                        StrategyObservation(
                            candidate=candidate,
                            terminal_return=outcome[0],
                            drawdown=outcome[1],
                            success=outcome[2],
                        )
                    )

        ranked_candidates: list[tuple[StrategyCandidate, int, float, float, float, float, bool]] = []
        for candidate, observations in observations_by_candidate.items():
            sample_size = len(observations)
            if sample_size < MIN_DISCOVERY_SAMPLE:
                continue
            returns = [item.terminal_return for item in observations]
            win_rate = sum(1 for item in observations if item.success) / sample_size
            avg_return = sum(returns) / sample_size
            sharpe_ratio = _sharpe_ratio(returns)
            max_drawdown = min(item.drawdown for item in observations)
            enabled = _strategy_enabled(sample_size, win_rate, avg_return, sharpe_ratio, max_drawdown)
            ranked_candidates.append(
                (candidate, sample_size, win_rate, avg_return, sharpe_ratio, max_drawdown, enabled)
            )

        ranked_candidates.sort(
            key=lambda item: (item[6], item[4], item[2], item[3], item[1], -item[5]),
            reverse=True,
        )
        ranked_candidates = ranked_candidates[:MAX_DISCOVERED_STRATEGIES]

        existing_rows = (
            (
                await self.session.execute(
                    select(Strategy).options(selectinload(Strategy.rules), selectinload(Strategy.performance))
                )
            )
            .scalars()
            .all()
        )
        existing_by_name = {row.name: row for row in existing_rows}
        seen_ids: set[int] = set()
        for candidate, sample_size, win_rate, avg_return, sharpe_ratio, max_drawdown, enabled in ranked_candidates:
            name = _strategy_name(candidate)
            row = existing_by_name.get(name)
            if row is None:
                row = Strategy(name=name, description=_strategy_description(candidate), enabled=enabled)
                self.session.add(row)
                await self._uow.flush()
                existing_by_name[name] = row
            else:
                row.description = _strategy_description(candidate)
                row.enabled = enabled
            await self.session.execute(delete(StrategyRule).where(StrategyRule.strategy_id == int(row.id)))
            self.session.add_all(
                [
                    StrategyRule(
                        strategy_id=int(row.id),
                        pattern_slug=token,
                        regime=candidate.regime,
                        sector=candidate.sector,
                        cycle=candidate.cycle,
                        min_confidence=candidate.min_confidence,
                    )
                    for token in candidate.tokens
                ]
            )
            performance = await self.session.get(StrategyPerformance, int(row.id))
            if performance is None:
                performance = StrategyPerformance(strategy_id=int(row.id))
                self.session.add(performance)
            performance.sample_size = sample_size
            performance.win_rate = win_rate
            performance.avg_return = avg_return
            performance.sharpe_ratio = sharpe_ratio
            performance.max_drawdown = max_drawdown
            performance.updated_at = utc_now()
            seen_ids.add(int(row.id))
        for row in existing_by_name.values():
            if int(row.id) not in seen_ids:
                row.enabled = False
        await self._uow.flush()
        return {
            "status": "ok",
            "strategies": len(ranked_candidates),
            "enabled": sum(1 for item in ranked_candidates if item[6]),
        }


__all__ = ["PatternMarketDiscoveryMixin"]
