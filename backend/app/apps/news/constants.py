from __future__ import annotations

NEWS_SOURCE_PLUGIN_X = "x"
NEWS_SOURCE_PLUGIN_TELEGRAM_USER = "telegram_user"
NEWS_SOURCE_PLUGIN_DISCORD_BOT = "discord_bot"
NEWS_SOURCE_PLUGIN_TRUTH_SOCIAL = "truth_social"

NEWS_SOURCE_STATUS_ACTIVE = "active"
NEWS_SOURCE_STATUS_DISABLED = "disabled"
NEWS_SOURCE_STATUS_ERROR = "error"

NEWS_EVENT_ITEM_INGESTED = "news_item_ingested"
NEWS_EVENT_ITEM_NORMALIZED = "news_item_normalized"
NEWS_EVENT_SYMBOL_CORRELATION_UPDATED = "news_symbol_correlation_updated"

NEWS_NORMALIZATION_STATUS_PENDING = "pending"
NEWS_NORMALIZATION_STATUS_NORMALIZED = "normalized"
NEWS_NORMALIZATION_STATUS_ERROR = "error"

DEFAULT_NEWS_POLL_LIMIT = 50
MAX_NEWS_POLL_LIMIT = 100
DEFAULT_X_API_BASE_URL = "https://api.x.com/2"
DEFAULT_DISCORD_API_BASE_URL = "https://discord.com/api/v10"

NEWS_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "macro": ("cpi", "fed", "rates", "inflation", "macro", "yield", "fomc"),
    "listing": ("listing", "listed", "launchpool", "perps", "futures", "listing roadmap"),
    "security": ("hack", "exploit", "drain", "breach", "incident"),
    "ai": ("ai", "agent", "gpu", "inference", "model"),
    "regulation": ("sec", "regulation", "lawsuit", "etf", "approval"),
}

NEWS_POSITIVE_KEYWORDS = (
    "breakout",
    "surge",
    "bullish",
    "beat",
    "upgrade",
    "partnership",
    "approval",
    "launch",
    "outperform",
)

NEWS_NEGATIVE_KEYWORDS = (
    "dump",
    "bearish",
    "hack",
    "exploit",
    "delay",
    "selloff",
    "risk",
    "lawsuit",
    "breach",
)
