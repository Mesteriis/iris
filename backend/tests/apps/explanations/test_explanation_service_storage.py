from __future__ import annotations

from src.apps.explanations.contracts import ExplanationArtifactResult
from src.apps.explanations.services.explanation_service import _explanation_storage_fields
from src.apps.explanations.services.generation_service import TEMPLATE_DEGRADED_STRATEGY
from src.core.ai.contracts import AICapability, AIContextFormat, AIValidationStatus
from src.core.ai.telemetry import AIExecutionMetadata
from src.core.i18n import MessageDescriptor


def test_explanation_storage_fields_drop_rendered_text_for_descriptor_backed_result() -> None:
    fields = _explanation_storage_fields(
        ExplanationArtifactResult(
            title="BTCUSDT: signal explanation",
            explanation="The breakout signal on 60m was recorded with confidence 0.82.",
            bullets=("Priority score is 0.91.", "Context score is 0.74."),
            metadata=_metadata(fallback_used=True, degraded_strategy=TEMPLATE_DEGRADED_STRATEGY),
            title_descriptor=MessageDescriptor(
                key="brief.explanation.signal.title",
                params={"symbol": "BTCUSDT", "timeframe": 60, "signal_type": "breakout", "confidence": 0.82},
            ),
            explanation_descriptor=MessageDescriptor(
                key="brief.explanation.signal.body",
                params={"symbol": "BTCUSDT", "timeframe": 60, "signal_type": "breakout", "confidence": 0.82},
            ),
            bullet_descriptors=(
                MessageDescriptor(
                    key="brief.explanation.signal.bullet.priority",
                    params={"priority_score": 0.91},
                ),
            ),
        ),
        rendered_locale="en",
    )

    assert fields["content_kind"] == "descriptor_bundle"
    assert fields["content_json"] == {
        "version": 1,
        "kind": "descriptor_bundle",
        "title": {
            "key": "brief.explanation.signal.title",
            "params": {"symbol": "BTCUSDT", "timeframe": 60, "signal_type": "breakout", "confidence": 0.82},
        },
        "explanation": {
            "key": "brief.explanation.signal.body",
            "params": {"symbol": "BTCUSDT", "timeframe": 60, "signal_type": "breakout", "confidence": 0.82},
        },
        "bullets": [
            {"key": "brief.explanation.signal.bullet.priority", "params": {"priority_score": 0.91}},
        ],
    }


def test_explanation_storage_fields_keep_text_for_non_descriptor_result() -> None:
    fields = _explanation_storage_fields(
        ExplanationArtifactResult(
            title="ETHUSDT decision explanation",
            explanation="The decision snapshot stays aligned with the stored machine reason.",
            bullets=("Confidence remains stable.", "Reason still drives the artifact."),
            metadata=_metadata(fallback_used=False, degraded_strategy=None),
        ),
        rendered_locale="en",
    )

    assert fields == {
        "content_kind": "generated_text",
        "content_json": {
            "version": 1,
            "kind": "generated_text",
            "rendered_locale": "en",
            "title": "ETHUSDT decision explanation",
            "explanation": "The decision snapshot stays aligned with the stored machine reason.",
            "bullets": ["Confidence remains stable.", "Reason still drives the artifact."],
        },
    }


def _metadata(*, fallback_used: bool, degraded_strategy: str | None) -> AIExecutionMetadata:
    return AIExecutionMetadata(
        capability=AICapability.EXPLAIN_GENERATE,
        task="explain_generate",
        requested_provider=None,
        actual_provider="local_test",
        model="llama-test",
        requested_language=None,
        effective_language="en",
        context_format=AIContextFormat.COMPACT_JSON,
        context_record_count=10,
        context_bytes=540,
        context_token_estimate=135,
        fallback_used=fallback_used,
        degraded_strategy=degraded_strategy,
        latency_ms=15,
        validation_status=AIValidationStatus.VALID,
        prompt_name="explain.signal",
        prompt_version=1,
    )
