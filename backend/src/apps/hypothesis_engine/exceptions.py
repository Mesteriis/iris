class HypothesisEngineError(Exception):
    """Base hypothesis engine error."""


class PromptNotFoundError(HypothesisEngineError):
    """Raised when a requested prompt version cannot be found."""


class UnsupportedLLMProviderError(HypothesisEngineError):
    """Raised when the configured provider name is unknown."""


class InvalidPromptPayloadError(HypothesisEngineError):
    """Raised when prompt CRUD payloads are invalid."""
