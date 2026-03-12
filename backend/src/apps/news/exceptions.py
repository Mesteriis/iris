class NewsSourceError(Exception):
    """Base news source exception."""


class UnsupportedNewsPluginError(NewsSourceError):
    """Raised when a plugin is intentionally unsupported."""


class InvalidNewsSourceConfigurationError(NewsSourceError):
    """Raised when a news source payload is incomplete or invalid."""


class TelegramOnboardingError(NewsSourceError):
    """Raised when Telegram onboarding fails."""
