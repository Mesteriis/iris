class AnomalyError(Exception):
    """Base anomaly domain error."""


class AnomalyContextUnavailable(AnomalyError):
    """Raised when the anomaly engine cannot build enough market context."""
