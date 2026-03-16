class MarketStructureError(Exception):
    """Base market structure domain error."""


class InvalidMarketStructureSourceConfigurationError(MarketStructureError):
    """Raised when a market structure source is misconfigured."""


class UnsupportedMarketStructurePluginError(MarketStructureError):
    """Raised when a requested market structure plugin is unsupported."""


class UnauthorizedMarketStructureIngestError(MarketStructureError):
    """Raised when a manual ingest request does not satisfy source-level auth."""


class InvalidMarketStructureWebhookPayloadError(MarketStructureError):
    """Raised when a webhook payload cannot be normalized into market structure snapshots."""
