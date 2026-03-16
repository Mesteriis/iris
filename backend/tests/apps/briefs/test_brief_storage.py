from src.apps.briefs.contracts import BriefArtifactResult
from src.apps.briefs.services.brief_service import _brief_storage_fields
from src.core.ai.contracts import AICapability, AIContextFormat, AIValidationStatus
from src.core.ai.telemetry import AIExecutionMetadata


def test_brief_storage_fields_use_generated_text_content_envelope() -> None:
    fields = _brief_storage_fields(
        BriefArtifactResult(
            title="Market brief",
            summary="Leaders remain constructive while breadth stays selective.",
            bullets=(
                "BTCUSD_EVT holds the strongest confidence profile.",
                "Broader breadth remains narrower than the headline momentum.",
            ),
            metadata=_metadata(),
        ),
        rendered_locale="en",
    )

    assert fields == {
        "content_kind": "generated_text",
        "content_json": {
            "version": 1,
            "kind": "generated_text",
            "rendered_locale": "en",
            "title": "Market brief",
            "summary": "Leaders remain constructive while breadth stays selective.",
            "bullets": [
                "BTCUSD_EVT holds the strongest confidence profile.",
                "Broader breadth remains narrower than the headline momentum.",
            ],
        },
    }


def _metadata() -> AIExecutionMetadata:
    return AIExecutionMetadata(
        capability=AICapability.BRIEF_GENERATE,
        task="brief_generate",
        requested_provider=None,
        actual_provider="local_test",
        model="llama-test",
        requested_language=None,
        effective_language="en",
        context_format=AIContextFormat.COMPACT_JSON,
        context_record_count=4,
        context_bytes=512,
        context_token_estimate=128,
        fallback_used=False,
        degraded_strategy=None,
        latency_ms=18,
        validation_status=AIValidationStatus.VALID,
        prompt_name="brief.market",
        prompt_version=1,
    )
