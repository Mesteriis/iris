from enum import Enum


class HistorySources(str, Enum):
    YFinance = "Yahoo Finance"
    KuCoin = "KuCoin"
    Kraken = "Kraken"
    Coinbase = "Coinbase"
    Binance = "Binance"
    CoinGecko = "CoinGecko"
