from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.briefs.contracts import BriefKind, build_scope_key
from src.apps.briefs.models import AIBrief
from src.apps.briefs.read_models import BriefContextBundle, BriefReadModel, brief_read_model_from_orm
from src.apps.market_data.models import Coin
from src.apps.portfolio.query_services import PortfolioQueryService
from src.apps.portfolio.read_models import portfolio_position_payload, portfolio_state_payload
from src.apps.signals.query_services import SignalQueryService
from src.apps.signals.read_models import coin_market_decision_payload, market_decision_payload
from src.core.ai import AIContextFormat
from src.core.db.persistence import AsyncQueryService
from src.core.http.analytics import latest_timestamp

_MARKET_BRIEF_LIMIT = 12
_PORTFOLIO_BRIEF_LIMIT = 12


class BriefQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="briefs", service_name="BriefQueryService")
        self._signals = SignalQueryService(session)
        self._portfolio = PortfolioQueryService(session)

    async def get_brief(
        self,
        *,
        brief_kind: BriefKind,
        scope_key: str,
        language: str,
    ) -> BriefReadModel | None:
        self._log_debug(
            "query.get_brief",
            mode="read",
            brief_kind=brief_kind.value,
            scope_key=scope_key,
            language=language,
        )
        row = await self.session.scalar(
            select(AIBrief)
            .where(
                AIBrief.brief_kind == brief_kind.value,
                AIBrief.scope_key == scope_key,
                AIBrief.language == language,
            )
            .limit(1)
        )
        if row is None:
            self._log_debug("query.get_brief.result", mode="read", found=False)
            return None
        item = brief_read_model_from_orm(row)
        self._log_debug("query.get_brief.result", mode="read", found=True)
        return item

    async def build_market_context(self) -> BriefContextBundle:
        self._log_debug("query.build_market_brief_context", mode="read", limit=_MARKET_BRIEF_LIMIT)
        items = await self._signals.list_top_market_decisions(limit=_MARKET_BRIEF_LIMIT)
        rows = [market_decision_payload(item) for item in items]
        decision_counts = Counter(str(row["decision"]).lower() for row in rows)
        source_updated_at = latest_timestamp(row.get("created_at") for row in rows)
        return BriefContextBundle(
            brief_kind=BriefKind.MARKET,
            scope_key=build_scope_key(BriefKind.MARKET),
            symbol=None,
            coin_id=None,
            source_updated_at=source_updated_at,
            preferred_context_format=AIContextFormat.CSV if rows else AIContextFormat.COMPACT_JSON,
            context={
                "brief_kind": BriefKind.MARKET.value,
                "scope_key": build_scope_key(BriefKind.MARKET),
                "rows": rows,
                "summary": {
                    "tracked_symbols": len(rows),
                    "decision_counts": dict(decision_counts),
                    "source_updated_at": source_updated_at,
                },
            },
            refs_json={
                "scope": "market",
                "top_symbols": [row["symbol"] for row in rows[:5]],
                "tracked_symbols": len(rows),
            },
        )

    async def build_symbol_context(self, symbol: str) -> BriefContextBundle | None:
        normalized_symbol = str(symbol).strip().upper()
        self._log_debug("query.build_symbol_brief_context", mode="read", symbol=normalized_symbol)
        item = await self._signals.get_coin_market_decision(normalized_symbol)
        if item is None:
            self._log_debug("query.build_symbol_brief_context.result", mode="read", found=False)
            return None
        payload = coin_market_decision_payload(item)
        source_updated_at = latest_timestamp(row.get("created_at") for row in payload.get("items", ()))
        bundle = BriefContextBundle(
            brief_kind=BriefKind.SYMBOL,
            scope_key=build_scope_key(BriefKind.SYMBOL, symbol=normalized_symbol),
            symbol=normalized_symbol,
            coin_id=int(payload["coin_id"]),
            source_updated_at=source_updated_at,
            preferred_context_format=AIContextFormat.COMPACT_JSON,
            context={
                "brief_kind": BriefKind.SYMBOL.value,
                "scope_key": build_scope_key(BriefKind.SYMBOL, symbol=normalized_symbol),
                **payload,
                "rows": list(payload["items"]),
                "summary": {
                    "timeframes": len(payload["items"]),
                    "source_updated_at": source_updated_at,
                },
            },
            refs_json={
                "scope": "symbol",
                "symbol": normalized_symbol,
                "coin_id": int(payload["coin_id"]),
                "canonical_decision": payload.get("canonical_decision"),
            },
        )
        self._log_debug("query.build_symbol_brief_context.result", mode="read", found=True)
        return bundle

    async def build_portfolio_context(self) -> BriefContextBundle:
        self._log_debug("query.build_portfolio_brief_context", mode="read", limit=_PORTFOLIO_BRIEF_LIMIT)
        state = await self._portfolio.get_state()
        positions = await self._portfolio.list_positions(limit=_PORTFOLIO_BRIEF_LIMIT)
        state_snapshot = portfolio_state_payload(state)
        rows = [portfolio_position_payload(item) for item in positions]
        total_position_value = sum(float(row.get("position_value") or 0.0) for row in rows)
        source_updated_at = latest_timestamp(
            [
                state_snapshot.get("updated_at"),
                *(row.get("opened_at") for row in rows),
                *(row.get("closed_at") for row in rows if row.get("closed_at") is not None),
            ]
        )
        return BriefContextBundle(
            brief_kind=BriefKind.PORTFOLIO,
            scope_key=build_scope_key(BriefKind.PORTFOLIO),
            symbol=None,
            coin_id=None,
            source_updated_at=source_updated_at,
            preferred_context_format=AIContextFormat.TOON if rows else AIContextFormat.COMPACT_JSON,
            context={
                "brief_kind": BriefKind.PORTFOLIO.value,
                "scope_key": build_scope_key(BriefKind.PORTFOLIO),
                "state": state_snapshot,
                "rows": rows,
                "summary": {
                    "tracked_positions": len(rows),
                    "total_position_value": total_position_value,
                    "source_updated_at": source_updated_at,
                },
            },
            refs_json={
                "scope": "portfolio",
                "open_positions": int(state.open_positions),
                "max_positions": int(state.max_positions),
                "tracked_positions": len(rows),
            },
        )

    async def symbol_exists(self, symbol: str) -> bool:
        normalized_symbol = str(symbol).strip().upper()
        self._log_debug("query.symbol_exists", mode="read", symbol=normalized_symbol)
        result = await self.session.scalar(select(Coin.id).where(Coin.symbol == normalized_symbol).limit(1))
        found = result is not None
        self._log_debug("query.symbol_exists.result", mode="read", symbol=normalized_symbol, found=found)
        return found


__all__ = ["BriefQueryService"]
