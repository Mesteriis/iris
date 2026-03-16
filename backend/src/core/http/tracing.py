from src.core.http.contracts import HttpContract


class TraceContext(HttpContract):
    request_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
