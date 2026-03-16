from unittest.mock import AsyncMock

import pytest
from iris.apps.notifications.contracts import NotificationHumanizationResult
from iris.apps.notifications.models import AINotification
from iris.apps.notifications.services.notification_service import NotificationService
from iris.apps.notifications.services.side_effects import NotificationSideEffectDispatcher
from iris.core.ai.contracts import AICapability, AIContextFormat, AIValidationStatus
from iris.core.ai.telemetry import AIExecutionMetadata
from iris.core.db.uow import SessionUnitOfWork
from iris.runtime.streams.types import IrisEvent
from sqlalchemy import select


@pytest.mark.asyncio
async def test_notification_service_persists_artifact_and_emits_created_event(
    async_db_session,
    seeded_market,
    monkeypatch,
) -> None:
    coin_id = int(seeded_market["ETHUSD_EVT"]["coin_id"])
    event_timestamp = seeded_market["ETHUSD_EVT"]["latest_timestamp"]

    generate = AsyncMock(
        return_value=NotificationHumanizationResult(
            title="ETHUSD: anomaly detected",
            message="IRIS flagged a volatility anomaly for ETHUSD.",
            severity="warning",
            urgency="high",
            metadata=AIExecutionMetadata(
                capability=AICapability.NOTIFICATION_HUMANIZE,
                task="notification_humanize",
                requested_provider=None,
                actual_provider="local_test",
                model="llama-test",
                requested_language=None,
                effective_language="en",
                context_format=AIContextFormat.JSON,
                context_record_count=8,
                context_bytes=256,
                context_token_estimate=64,
                fallback_used=False,
                degraded_strategy=None,
                latency_ms=42,
                validation_status=AIValidationStatus.VALID,
                prompt_name="notification.anomaly_detected",
                prompt_version=1,
            ),
        )
    )
    published: list[tuple[str, dict[str, object]]] = []

    monkeypatch.setattr(
        "iris.apps.notifications.services.notification_service.NotificationHumanizationService.generate",
        generate,
    )
    monkeypatch.setattr(
        "iris.apps.notifications.services.side_effects.publish_event",
        lambda event_type, payload: published.append((event_type, payload)),
    )

    event = IrisEvent(
        stream_id="173-0",
        event_type="anomaly_detected",
        coin_id=coin_id,
        timeframe=15,
        timestamp=event_timestamp,
        payload={
            "anomaly_type": "volatility_regime_break",
            "score": 0.91,
        },
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        result = await NotificationService(uow).create_from_event(event)
        await uow.commit()
    await NotificationSideEffectDispatcher().apply_creation(result)

    notification = await async_db_session.scalar(
        select(AINotification).where(AINotification.id == int(result.notification_id or 0))
    )
    assert notification is not None
    assert notification.severity == "warning"
    assert notification.urgency == "high"
    assert notification.content_kind == "generated_text"
    assert notification.content_json["rendered_locale"] == "en"
    assert notification.content_json["title"] == "ETHUSD: anomaly detected"
    assert notification.context_json["ai_execution"]["validation_status"] == "valid"
    assert notification.refs_json["canonical_fields"]["anomaly_type"] == "volatility_regime_break"
    assert published == [
        (
            "notification_created",
            {
                "coin_id": coin_id,
                "timeframe": 15,
                "timestamp": event_timestamp,
                "notification_id": int(result.notification_id or 0),
                "severity": "warning",
                "urgency": "high",
                "source_event_type": "anomaly_detected",
            },
        )
    ]


@pytest.mark.asyncio
async def test_notification_service_is_idempotent_for_same_event(async_db_session, seeded_market, monkeypatch) -> None:
    coin_id = int(seeded_market["BTCUSD_EVT"]["coin_id"])
    event_timestamp = seeded_market["BTCUSD_EVT"]["latest_timestamp"]
    generate = AsyncMock(
        return_value=NotificationHumanizationResult(
            title="BTCUSD: new signal",
            message="IRIS detected a momentum signal for BTCUSD.",
            severity="info",
            urgency="medium",
            metadata=AIExecutionMetadata(
                capability=AICapability.NOTIFICATION_HUMANIZE,
                task="notification_humanize",
                requested_provider=None,
                actual_provider="local_test",
                model="llama-test",
                requested_language=None,
                effective_language="en",
                context_format=AIContextFormat.JSON,
                context_record_count=8,
                context_bytes=256,
                context_token_estimate=64,
                fallback_used=False,
                degraded_strategy=None,
                latency_ms=21,
                validation_status=AIValidationStatus.VALID,
                prompt_name="notification.signal_created",
                prompt_version=1,
            ),
        )
    )
    monkeypatch.setattr(
        "iris.apps.notifications.services.notification_service.NotificationHumanizationService.generate",
        generate,
    )
    monkeypatch.setattr("iris.apps.notifications.services.side_effects.publish_event", lambda *_args, **_kwargs: None)

    event = IrisEvent(
        stream_id="174-0",
        event_type="signal_created",
        coin_id=coin_id,
        timeframe=15,
        timestamp=event_timestamp,
        payload={"signal_type": "pattern_breakout"},
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        service = NotificationService(uow)
        first = await service.create_from_event(event)
        second = await service.create_from_event(event)
        await uow.commit()

    rows = (
        await async_db_session.execute(
            select(AINotification).where(
                AINotification.source_event_type == "signal_created",
                AINotification.source_event_id == event.event_id,
            )
        )
    ).scalars().all()
    assert first.notification_id == second.notification_id
    assert len(rows) == 1
    assert generate.await_count == 1
