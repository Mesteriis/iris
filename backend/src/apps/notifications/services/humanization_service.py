from __future__ import annotations

from typing import Any

from src.apps.notifications.constants import (
    NOTIFICATION_SEVERITY_VALUES,
    NOTIFICATION_URGENCY_VALUES,
    TEMPLATE_DEGRADED_STRATEGY,
)
from src.apps.notifications.contracts import NotificationHumanizationOutput
from src.apps.notifications.prompts import NOTIFICATION_OUTPUT_SCHEMA, load_notification_prompt
from src.core.ai import (
    AICapability,
    AIExecutionRequest,
    AIExecutor,
    CallableDegradedStrategy,
    PydanticOutputValidator,
    get_capability_policy,
)
from src.core.settings import Settings, get_settings

_SUPPORTED_LANGUAGES = {"en", "ru", "es", "uk"}
_LANGUAGE_ALIASES = {"ua": "uk"}


def normalize_language(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower().replace("_", "-")
    if not normalized:
        return None
    normalized = _LANGUAGE_ALIASES.get(normalized, normalized)
    primary = normalized.split("-", maxsplit=1)[0]
    if primary in _LANGUAGE_ALIASES:
        primary = _LANGUAGE_ALIASES[primary]
    return primary if primary in _SUPPORTED_LANGUAGES else "en"


def resolve_requested_language(ctx: dict[str, Any]) -> str | None:
    for key in ("language", "locale"):
        normalized = normalize_language(ctx.get(key))
        if normalized is not None:
            return normalized
    return None


def resolve_effective_language(ctx: dict[str, Any], *, settings: Settings | None = None) -> str:
    requested = resolve_requested_language(ctx)
    if requested is not None:
        return requested
    effective_settings = settings or get_settings()
    default_language = normalize_language(getattr(effective_settings.language, "value", effective_settings.language))
    return default_language or "en"


class NotificationHumanizationService:
    def __init__(self, *, executor: AIExecutor | None = None, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._executor = executor or AIExecutor(settings=self._settings)

    async def generate(self, ctx: dict[str, Any]) -> dict[str, Any]:
        event_type = str(ctx.get("event_type") or "")
        prompt = load_notification_prompt(event_type)
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
        return {
            "title": str(payload.get("title") or ""),
            "message": str(payload.get("message") or ""),
            "severity": str(payload.get("severity") or "info"),
            "urgency": str(payload.get("urgency") or "medium"),
            "provider": str(metadata.actual_provider or TEMPLATE_DEGRADED_STRATEGY),
            "requested_provider": metadata.requested_provider,
            "model": metadata.model,
            "requested_language": metadata.requested_language,
            "effective_language": metadata.effective_language,
            "context_format": metadata.context_format.value,
            "context_record_count": metadata.context_record_count,
            "context_bytes": metadata.context_bytes,
            "context_token_estimate": metadata.context_token_estimate,
            "fallback_used": metadata.fallback_used,
            "degraded_strategy": metadata.degraded_strategy,
            "latency_ms": metadata.latency_ms,
            "validation_status": metadata.validation_status.value,
            "prompt_name": metadata.prompt_name,
            "prompt_version": int(metadata.prompt_version),
        }

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
    symbol = str(context.get("symbol") or payload.get("symbol") or "asset").upper()
    timeframe = max(int(context.get("timeframe") or 0), 1)
    severity, urgency = _classify_event(event_type=event_type, payload=payload)
    title, message = _render_event_text(
        event_type=event_type,
        payload=payload,
        symbol=symbol,
        timeframe=timeframe,
        language=language,
    )
    return {
        "title": title,
        "message": message,
        "severity": severity,
        "urgency": urgency,
    }


def _classify_event(*, event_type: str, payload: dict[str, Any]) -> tuple[str, str]:
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
    event_type: str,
    payload: dict[str, Any],
    symbol: str,
    timeframe: int,
    language: str,
) -> tuple[str, str]:
    decision = str(payload.get("decision") or "review").upper()
    score = _format_score(payload.get("score"))
    anomaly_type = str(payload.get("anomaly_type") or "anomaly").replace("_", " ")
    signal_type = str(payload.get("signal_type") or "signal").replace("_", " ")
    regime = str(payload.get("regime") or payload.get("market_regime") or "updated").replace("_", " ")
    exchange = str(payload.get("exchange_name") or payload.get("exchange") or "exchange")
    balance = _format_balance(payload.get("balance"))
    value_usd = _format_usd(payload.get("value_usd"))

    if language == "ru":
        if event_type == "signal_created":
            return (
                f"{symbol}: новый сигнал",
                f"IRIS зафиксировал сигнал {signal_type} по {symbol} на таймфрейме {timeframe}м. Проверь канонический сигнал перед действием.",
            )
        if event_type == "anomaly_detected":
            return (
                f"{symbol}: обнаружена аномалия",
                f"IRIS отметил аномалию {anomaly_type} по {symbol} на таймфрейме {timeframe}м. Проверь детерминированный контекст перед решением.",
            )
        if event_type == "decision_generated":
            return (
                f"{symbol}: новое решение",
                f"IRIS сгенерировал решение {decision} по {symbol} на таймфрейме {timeframe}м. Текущий score: {score}.",
            )
        if event_type == "market_regime_changed":
            return (
                f"{symbol}: режим рынка изменился",
                f"Для {symbol} на таймфрейме {timeframe}м режим рынка сменился на {regime}. Проверь машинный контекст перед ребалансировкой.",
            )
        if event_type == "portfolio_position_changed":
            return (
                f"{symbol}: позиция обновлена",
                f"Состояние позиции по {symbol} обновилось на {exchange}. Текущая стоимость: {value_usd}.",
            )
        if event_type == "portfolio_balance_updated":
            return (
                f"{symbol}: баланс обновлен",
                f"Синхронизация баланса обновила {symbol} на {exchange}. Баланс: {balance}, стоимость: {value_usd}.",
            )
        return (f"{symbol}: обновление", f"IRIS зафиксировал событие {event_type} по {symbol}.")

    if language == "es":
        if event_type == "signal_created":
            return (
                f"{symbol}: nueva senal",
                f"IRIS detecto la senal {signal_type} para {symbol} en {timeframe}m. Revisa la senal canonica antes de actuar.",
            )
        if event_type == "anomaly_detected":
            return (
                f"{symbol}: anomalia detectada",
                f"IRIS marco la anomalia {anomaly_type} para {symbol} en {timeframe}m. Revisa el contexto determinista antes de decidir.",
            )
        if event_type == "decision_generated":
            return (
                f"{symbol}: nueva decision",
                f"IRIS genero una decision {decision} para {symbol} en {timeframe}m. Score actual: {score}.",
            )
        if event_type == "market_regime_changed":
            return (
                f"{symbol}: cambio de regimen",
                f"El regimen de mercado para {symbol} cambio a {regime} en {timeframe}m. Revisa el contexto canonico antes de rebalancear.",
            )
        if event_type == "portfolio_position_changed":
            return (
                f"{symbol}: posicion actualizada",
                f"La posicion de cartera para {symbol} cambio en {exchange}. Valor actual: {value_usd}.",
            )
        if event_type == "portfolio_balance_updated":
            return (
                f"{symbol}: saldo actualizado",
                f"La sincronizacion actualizo {symbol} en {exchange}. Saldo: {balance}, valor: {value_usd}.",
            )
        return (f"{symbol}: actualizacion", f"IRIS registro el evento {event_type} para {symbol}.")

    if language == "uk":
        if event_type == "signal_created":
            return (
                f"{symbol}: новий сигнал",
                f"IRIS зафіксував сигнал {signal_type} для {symbol} на таймфреймі {timeframe}хв. Перевір канонічний сигнал перед дією.",
            )
        if event_type == "anomaly_detected":
            return (
                f"{symbol}: виявлено аномалію",
                f"IRIS позначив аномалію {anomaly_type} для {symbol} на таймфреймі {timeframe}хв. Перевір детермінований контекст перед рішенням.",
            )
        if event_type == "decision_generated":
            return (
                f"{symbol}: нове рішення",
                f"IRIS згенерував рішення {decision} для {symbol} на таймфреймі {timeframe}хв. Поточний score: {score}.",
            )
        if event_type == "market_regime_changed":
            return (
                f"{symbol}: ринок змінив режим",
                f"Для {symbol} на таймфреймі {timeframe}хв режим ринку змінився на {regime}. Перевір машинний контекст перед ребалансом.",
            )
        if event_type == "portfolio_position_changed":
            return (
                f"{symbol}: позицію оновлено",
                f"Стан позиції для {symbol} оновився на {exchange}. Поточна вартість: {value_usd}.",
            )
        if event_type == "portfolio_balance_updated":
            return (
                f"{symbol}: баланс оновлено",
                f"Синхронізація балансу оновила {symbol} на {exchange}. Баланс: {balance}, вартість: {value_usd}.",
            )
        return (f"{symbol}: оновлення", f"IRIS зафіксував подію {event_type} для {symbol}.")

    if event_type == "signal_created":
        return (
            f"{symbol}: new signal",
            f"IRIS detected the {signal_type} signal for {symbol} on {timeframe}m. Review the canonical signal before acting.",
        )
    if event_type == "anomaly_detected":
        return (
            f"{symbol}: anomaly detected",
            f"IRIS flagged the {anomaly_type} anomaly for {symbol} on {timeframe}m. Check the deterministic context before taking action.",
        )
    if event_type == "decision_generated":
        return (
            f"{symbol}: new decision",
            f"IRIS generated a {decision} decision for {symbol} on {timeframe}m. Current score: {score}.",
        )
    if event_type == "market_regime_changed":
        return (
            f"{symbol}: regime changed",
            f"Market regime for {symbol} moved to {regime} on {timeframe}m. Review the machine context before rebalancing.",
        )
    if event_type == "portfolio_position_changed":
        return (
            f"{symbol}: position updated",
            f"Portfolio position for {symbol} changed on {exchange}. Current value: {value_usd}.",
        )
    if event_type == "portfolio_balance_updated":
        return (
            f"{symbol}: balance updated",
            f"Balance sync updated {symbol} on {exchange}. Balance: {balance}, value: {value_usd}.",
        )
    return (f"{symbol}: update", f"IRIS recorded the {event_type} event for {symbol}.")


def _format_score(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.2f}"


def _format_usd(value: object) -> str:
    if value is None:
        return "n/a"
    return f"${float(value):.2f}"


def _format_balance(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.6g}"


__all__ = [
    "NotificationHumanizationService",
    "normalize_language",
    "render_template_notification",
    "resolve_effective_language",
    "resolve_requested_language",
]
