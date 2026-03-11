from miner.constants import AssetType
from miner.constants.history_source import HistorySources as HSources

MAP_ASSETS_TO_PROVIDERS = {
    # Crypto
    AssetType.BTC: [
        HSources.Binance,
        HSources.Kraken,
        HSources.KuCoin,
        HSources.Coinbase,
        HSources.CoinGecko,
        HSources.YFinance,
    ],
    AssetType.ETH: [
        HSources.Binance,
        HSources.Kraken,
        HSources.KuCoin,
        HSources.Coinbase,
        HSources.CoinGecko,
        HSources.YFinance,
    ],
    # Форекс: только Yahoo Finance
    AssetType.EURUSD: [HSources.YFinance],
    AssetType.GBPUSD: [HSources.YFinance],
    AssetType.CADUSD: [HSources.YFinance],
    AssetType.NZDUSD: [HSources.YFinance],
    AssetType.CHFUSD: [HSources.YFinance],
    # Metals: только Yahoo Finance
    AssetType.XAUUSD: [HSources.YFinance],
    AssetType.XAGUSD: [HSources.YFinance],
}
