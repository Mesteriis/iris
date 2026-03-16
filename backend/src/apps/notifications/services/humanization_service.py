from typing import Any, Literal, Protocol, cast, runtime_checkable

from src.apps.hypothesis_engine.prompts import LoadedPrompt
from src.apps.notifications.constants import (
    NOTIFICATION_SEVERITY_VALUES,
    NOTIFICATION_URGENCY_VALUES,
    TEMPLATE_DEGRADED_STRATEGY,
)
from src.apps.notifications.contracts import NotificationHumanizationOutput, NotificationHumanizationResult
from src.apps.notifications.prompts import NOTIFICATION_OUTPUT_SCHEMA
from src.core.ai import (
    AICapability,
    AIExecutionRequest,
    AIExecutor,
    CallableDegradedStrategy,
    PydanticOutputValidator,
    get_capability_policy,
)
from src.core.i18n import (
    MessageDescriptor,
    get_translation_service,
    normalize_language,
    resolve_effective_language,
    resolve_requested_language,
)
from src.core.settings import Settings, get_settings

type NotificationSeverity = Literal["info", "warning", "critical"]
type NotificationUrgency = Literal["low", "medium", "high"]


@runtime_checkable
class _SupportsInt(Protocol):
    def __int__(self) -> int: ...


@runtime_checkable
class _SupportsFloat(Protocol):
    def __float__(self) -> float: ...


class NotificationHumanizationService:
    def __init__(self, *, executor: AIExecutor | None = None, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._executor = executor or AIExecutor(settings=self._settings)

    async def generate(self, ctx: dict[str, Any], *, prompt: LoadedPrompt) -> NotificationHumanizationResult:
        event_type = str(ctx.get("event_type") or "")
        merged_ctx = {**prompt.vars_json, **ctx}
        policy = get_capability_policy(AICapability.NOTIFICATION_HUMANIZE, settings=self._settings)
        validator = PydanticOutputValidator(
            contract_name="notification.output.v1",
            schema_contract=NOTIFICATION_OUTPUT_SCHEMA,
            model=NotificationHumanizationOutput,
            semantic_validator=self._validate_output,
        )
        degraded_strategy = CallableDegradedStrategy(
            name=TEMPLATE_DEGRADED_STRATEGY,
            handler=self._run_template_fallback,
        )
        result = await self._executor.execute(
            AIExecutionRequest(
                capability=AICapability.NOTIFICATION_HUMANIZE,
                task=str(prompt.task),
                prompt_name=prompt.name,
                prompt_version=int(prompt.version),
                prompt_template=prompt.template,
                context=merged_ctx,
                validator=validator,
                prompt_vars=dict(prompt.vars_json),
                requested_language=resolve_requested_language(merged_ctx),
                requested_provider=self._resolve_requested_provider(merged_ctx),
                preferred_context_format=policy.preferred_context_format,
                allowed_context_formats=policy.allowed_context_formats,
                degraded_strategy=degraded_strategy,
                allow_degraded_fallback=policy.allow_degraded_fallback,
                source_event_type=event_type or None,
                source_event_id=self._string_or_none(merged_ctx.get("event_id")),
                source_stream_id=self._string_or_none(merged_ctx.get("stream_id")),
                causation_id=self._string_or_none(merged_ctx.get("causation_id")),
                correlation_id=self._string_or_none(merged_ctx.get("correlation_id")),
            )
        )
        payload = result.payload
        metadata = result.metadata
        title_descriptor = None
        message_descriptor = None
        if metadata.fallback_used and metadata.degraded_strategy == TEMPLATE_DEGRADED_STRATEGY:
            title_descriptor, message_descriptor = _describe_event_text(merged_ctx)
        title = str(payload.get("title") or "")
        message = str(payload.get("message") or "")
        if title_descriptor is not None and message_descriptor is not None:
            title = ""
            message = ""
        return NotificationHumanizationResult(
            title=title,
            message=message,
            severity=_coerce_notification_severity(payload.get("severity")),
            urgency=_coerce_notification_urgency(payload.get("urgency")),
            metadata=metadata,
            title_descriptor=title_descriptor,
            message_descriptor=message_descriptor,
        )

    def _validate_output(self, payload: NotificationHumanizationOutput, requested_language: str | None, effective_language: str) -> None:
        del requested_language, effective_language
        if not payload.title.strip():
            raise ValueError("Notification title must not be blank.")
        if not payload.message.strip():
            raise ValueError("Notification message must not be blank.")
        if len(payload.title.strip()) > 160:
            raise ValueError("Notification title is too long.")
        if len(payload.message.strip()) > 420:
            raise ValueError("Notification message is too long.")
        if payload.severity not in NOTIFICATION_SEVERITY_VALUES:
            raise ValueError("Unsupported notification severity.")
        if payload.urgency not in NOTIFICATION_URGENCY_VALUES:
            raise ValueError("Unsupported notification urgency.")

    async def _run_template_fallback(
        self,
        capability: AICapability,
        task: str,
        context: dict[str, Any],
        requested_language: str | None,
        effective_language: str,
    ) -> dict[str, Any]:
        del capability, task, requested_language
        return render_template_notification(context, effective_language=effective_language)

    def _resolve_requested_provider(self, ctx: dict[str, Any]) -> str | None:
        value = ctx.get("requested_provider")
        if value is None or not str(value).strip():
            return None
        return str(value).strip()

    def _string_or_none(self, value: object) -> str | None:
        if value is None or not str(value).strip():
            return None
        return str(value).strip()


def render_template_notification(context: dict[str, Any], *, effective_language: str) -> dict[str, Any]:
    language = normalize_language(effective_language) or "en"
    event_type = str(context.get("event_type") or "")
    payload = dict(context.get("payload") or {})
    title_descriptor, message_descriptor = _describe_event_text(context)
    severity, urgency = _classify_event(event_type=event_type, payload=payload)
    title, message = _render_event_text(
        title_descriptor=title_descriptor,
        message_descriptor=message_descriptor,
        language=language,
    )
    return {
        "title": title,
        "message": message,
        "severity": severity,
        "urgency": urgency,
    }


def _classify_event(*, event_type: str, payload: dict[str, Any]) -> tuple[NotificationSeverity, NotificationUrgency]:
    if event_type == "anomaly_detected":
        anomaly_type = str(payload.get("anomaly_type") or "").lower()
        if "liquidation" in anomaly_type or "cascade" in anomaly_type:
            return "critical", "high"
        return "warning", "high"
    if event_type == "decision_generated":
        decision = str(payload.get("decision") or "").lower()
        if decision in {"sell", "reduce", "exit", "avoid"}:
            return "warning", "high"
        return "info", "medium"
    if event_type == "market_regime_changed":
        regime = str(payload.get("regime") or payload.get("market_regime") or "").lower()
        if regime in {"bear", "bearish", "risk_off", "distribution"}:
            return "warning", "high"
        return "info", "medium"
    if event_type == "portfolio_position_changed":
        value_usd = float(payload.get("value_usd") or 0.0)
        if value_usd <= 0:
            return "warning", "medium"
        return "info", "medium"
    if event_type == "portfolio_balance_updated":
        return "info", "low"
    if event_type == "signal_created":
        signal_type = str(payload.get("signal_type") or "").lower()
        if "breakdown" in signal_type or "reversal" in signal_type:
            return "warning", "medium"
        return "info", "medium"
    return "info", "medium"


def _render_event_text(
    *,
    title_descriptor: MessageDescriptor,
    message_descriptor: MessageDescriptor,
    language: str,
) -> tuple[str, str]:
    translator = get_translation_service()
    return (
        translator.translate(title_descriptor.key, locale=language, params=dict(title_descriptor.params)).text,
        translator.translate(message_descriptor.key, locale=language, params=dict(message_descriptor.params)).text,
    )


def _notification_template_keys(event_type: str) -> tuple[str, str]:
    if event_type == "signal_created":
        return "notification.signal.created.title", "notification.signal.created.message"
    if event_type == "anomaly_detected":
        return "notification.anomaly.detected.title", "notification.anomaly.detected.message"
    if event_type == "decision_generated":
        return "notification.decision.generated.title", "notification.decision.generated.message"
    if event_type == "market_regime_changed":
        return "notification.market_regime.changed.title", "notification.market_regime.changed.message"
    if event_type == "portfolio_position_changed":
        return "notification.portfolio_position.changed.title", "notification.portfolio_position.changed.message"
    if event_type == "portfolio_balance_updated":
        return "notification.portfolio_balance.updated.title", "notification.portfolio_balance.updated.message"
    return "notification.event.generic.title", "notification.event.generic.message"


def _describe_event_text(context: dict[str, Any]) -> tuple[MessageDescriptor, MessageDescriptor]:
    event_type = str(context.get("event_type") or "")
    payload = dict(context.get("payload") or {})
    symbol = str(context.get("symbol") or payload.get("symbol") or "asset").upper()
    timeframe = max(int(context.get("timeframe") or 0), 1)
    title_key, message_key = _notification_template_keys(event_type)
    params = {
        "symbol": symbol,
        "timeframe": timeframe,
        "event_type": event_type,
        "decision": str(payload.get("decision") or "review").upper(),
        "score": _format_score(payload.get("score")),
        "anomaly_type": str(payload.get("anomaly_type") or "anomaly").replace("_", " "),
        "signal_type": str(payload.get("signal_type") or "signal").replace("_", " "),
        "regime": str(payload.get("regime") or payload.get("market_regime") or "updated").replace("_", " "),
        "exchange": str(payload.get("exchange_name") or payload.get("exchange") or "exchange"),
        "balance": _format_balance(payload.get("balance")),
        "value_usd": _format_usd(payload.get("value_usd")),
    }
    return (
        MessageDescriptor(key=title_key, params=params),
        MessageDescriptor(key=message_key, params=params),
    )


def _format_score(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{_required_float(value, field_name='score'):.2f}"


def _format_usd(value: object) -> str:
    if value is None:
        return "n/a"
    return f"${_required_float(value, field_name='value_usd'):.2f}"


def _format_balance(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{_required_float(value, field_name='balance'):.6g}"


def _coerce_notification_severity(value: object) -> NotificationSeverity:
    normalized = str(value or "info")
    if normalized in NOTIFICATION_SEVERITY_VALUES:
        return cast(NotificationSeverity, normalized)
    return "info"


def _coerce_notification_urgency(value: object) -> NotificationUrgency:
    normalized = str(value or "medium")
    if normalized in NOTIFICATION_URGENCY_VALUES:
        return cast(NotificationUrgency, normalized)
    return "medium"


def _required_float(value: object, *, field_name: str) -> float:
    if isinstance(value, bool | int | float | str | bytes | bytearray):
        return float(value)
    if isinstance(value, _SupportsFloat):
        return float(value)
    if isinstance(value, _SupportsInt):
        return float(int(value))
    raise TypeError(f"{field_name} must be float-compatible, got {type(value).__name__}")


__all__ = [
    "NotificationHumanizationService",
    "normalize_language",
    "render_template_notification",
    "resolve_effective_language",
    "resolve_requested_language",
]
