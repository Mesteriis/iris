#!/usr/bin/env python3
"""
CoinGecko провайдер данных для MANTIS майнера
"""

import asyncio
from datetime import datetime
from logging import getLogger

import httpx

from ..constants.history_source import HistorySources
from ..tools.http_client import request
from .base import BaseDataProvider, DataPoint

history_logger = getLogger("history")
logger = getLogger("data")


class CoinGeckoProvider(BaseDataProvider):
    """
    Провайдер данных CoinGecko

    Особенности:
    - Бесплатная версия поддерживает только дневные данные
    - Лимит 365 дней на запрос
    - Rate limit: 10-30 запросов в минуту
    """

    def _init_provider(self):
        """Инициализация провайдера CoinGecko"""
        self.name = HistorySources.CoinGecko
        self.base_url = "https://api.coingecko.com/api/v3"

        # CoinGecko использует собственные ID монет
        self._asset_symbols = {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "ADA": "cardano",
            "DOT": "polkadot",
            "SOL": "solana",
            "AVAX": "avalanche-2",
            "MATIC": "matic-network",
            "LINK": "chainlink",
            "UNI": "uniswap",
            "AAVE": "aave",
            "COMP": "compound-governance-token",
            "MKR": "maker",
            "CRV": "curve-dao-token",
            "LTC": "litecoin",
            "BCH": "bitcoin-cash",
            "XLM": "stellar",
            "ETC": "ethereum-classic",
            "TRX": "tron",
            "SUSHI": "sushi",
            "1INCH": "1inch",
            "MANA": "decentraland",
            "SAND": "the-sandbox",
            "ENJ": "enjincoin",
            "BAT": "basic-attention-token",
            "ZEC": "zcash",
            "DASH": "dash",
            "XMR": "monero",
            # Forex пары (CoinGecko не поддерживает напрямую)
            "EURUSD": None,
            "GBPUSD": None,
            "USDJPY": None,
            "USDCHF": None,
            "AUDUSD": None,
            "USDCAD": None,
            "NZDUSD": None,
        }

        # Убираем Forex пары (CoinGecko их не поддерживает)
        self._supported_assets = {k for k, v in self._asset_symbols.items() if v is not None}

        # CoinGecko поддерживает только дневные данные в бесплатной версии
        # Для минутных/часовых данных нужна Pro версия
        self._supported_intervals = ["1d"]

    async def fetch_historical_data(self, symbol: str, interval: str = "1d", limit: int = 100) -> list[DataPoint]:
        """
        Получает данные от CoinGecko API с поддержкой множественных запросов

        CoinGecko бесплатная версия ограничена 365 днями на запрос.
        Для получения больше данных делаем несколько запросов с разными временными диапазонами.
        """

        # CoinGecko ID для монеты
        coin_id = symbol

        # CoinGecko бесплатная версия ограничена 365 днями на запрос
        max_days_per_request = 365

        if limit <= max_days_per_request:
            # Простой случай - один запрос
            return await self._fetch_single_batch_gecko(coin_id, limit)
        else:
            # Сложный случай - несколько запросов
            return await self._fetch_multiple_batches_gecko(coin_id, limit, max_days_per_request)

    async def _fetch_single_batch_gecko(self, coin_id: str, days: int) -> list[DataPoint]:
        """Выполняет один запрос к CoinGecko API"""
        url = f"{self.base_url}/coins/{coin_id}/ohlc"
        params = {
            "vs_currency": "usd",
            "days": days,
        }

        history_logger.debug("📊 %s: один запрос %s дней для %s", self.name, days, coin_id)

        try:
            response = await request("GET", url, params=params, timeout=10.0, max_retries=1)
            response.raise_for_status()
            data = response.json()

            return self._parse_coingecko_data(data, coin_id)

        except httpx.TimeoutException:
            history_logger.warning("⏰ %s: таймаут при получении данных для %s", self.name, coin_id)
            return []
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                history_logger.warning("🚫 %s: превышен rate limit для %s", self.name, coin_id)
            else:
                history_logger.error("🌐 %s: HTTP ошибка %s для %s", self.name, e.response.status_code, coin_id)
            return []
        except Exception as e:
            history_logger.error("❌ %s: ошибка получения данных для %s: %s", self.name, coin_id, e)
            return []

    async def _fetch_multiple_batches_gecko(
        self, coin_id: str, total_days: int, max_days_per_request: int
    ) -> list[DataPoint]:
        """Выполняет несколько запросов для получения большого количества дней"""
        # Высчитываем сколько запросов нужно
        batches_needed = (total_days + max_days_per_request - 1) // max_days_per_request

        history_logger.debug(
            "%s: множественный запрос %s дней для %s (%s батчей)", self.name, total_days, coin_id, batches_needed
        )

        all_results = []

        try:
            # CoinGecko API не поддерживает точное смещение по дням
            # Делаем запросы с увеличивающимся диапазоном дней
            for batch_num in range(batches_needed):
                # Запрашиваем всё больше дней в каждом запросе
                batch_days = min(max_days_per_request * (batch_num + 1), total_days)

                url = f"{self.base_url}/coins/{coin_id}/ohlc"
                params = {
                    "vs_currency": "usd",
                    "days": batch_days,
                }

                history_logger.debug(
                    "📊 %s: батч %s/%s для %s (%s дней)", self.name, batch_num + 1, batches_needed, coin_id, batch_days
                )

                response = await request("GET", url, params=params, timeout=10.0, max_retries=1)
                response.raise_for_status()
                batch_data = response.json()

                if batch_data:
                    # Каждый запрос дает данные с начала периода, поэтому берем только новые
                    parsed_batch = self._parse_coingecko_data(batch_data, coin_id)

                    # На первом запросе берем все данные
                    if batch_num == 0:
                        all_results = parsed_batch
                    elif all_results:
                        oldest_timestamp = min(dp.timestamp for dp in all_results)
                        new_points = [dp for dp in parsed_batch if dp.timestamp < oldest_timestamp]
                        all_results.extend(new_points)
                    else:
                        all_results = parsed_batch
                else:
                    history_logger.warning("⚠️ %s: пустой батч %s для %s", self.name, batch_num + 1, coin_id)
                    break

                # Проверяем достигли ли нужного количества
                if len(all_results) >= total_days:
                    break

                # Rate limiting для CoinGecko
                await self._rate_limit()

            # Сортируем все результаты по времени и ограничиваем
            all_results.sort(key=lambda x: x.timestamp)
            final_result = all_results[-total_days:] if len(all_results) > total_days else all_results

            history_logger.debug(
                "%s: собрано %s точек из %s батчей (запрошено %s)",
                self.name,
                len(final_result),
                batches_needed,
                total_days,
            )

            return final_result

        except Exception as e:
            history_logger.error("❌ %s: ошибка множественного запроса для %s: %s", self.name, coin_id, e)
            return []

    def _parse_coingecko_data(self, data: list, coin_id: str) -> list[DataPoint]:
        """Парсит данные CoinGecko в формат DataPoint"""
        result = []

        for item in data:
            if len(item) != 5:
                continue

            timestamp_ms = int(item[0])

            data_point = DataPoint(
                timestamp=timestamp_ms,
                open=float(item[1]),
                high=float(item[2]),
                low=float(item[3]),
                close=float(item[4]),
                volume=0.0,  # OHLC endpoint не возвращает объем
                datetime=datetime.fromtimestamp(timestamp_ms / 1000),
                source=self.name,
                asset="",  # Будет заполнено в базовом классе
                original_symbol=coin_id,
            )
            result.append(data_point)

        return result

    async def _rate_limit(self):
        """Rate limiting для CoinGecko - 10-30 запросов в минуту для бесплатной версии"""
        await asyncio.sleep(3.5)  # ~17 запросов в минуту для более стабильной работы
