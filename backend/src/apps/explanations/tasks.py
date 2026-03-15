from __future__ import annotations

from src.apps.explanations.contracts import ExplainKind, ExplanationGenerationResult
from src.apps.explanations.language import resolve_effective_language
from src.apps.explanations.services import ExplanationService
from src.core.db.uow import AsyncUnitOfWork
from src.core.http.operation_store import OperationStore, run_tracked_operation
from src.runtime.orchestration.broker import broker
from src.runtime.orchestration.locks import async_redis_task_lock

EXPLANATION_GENERATION_LOCK_TIMEOUT_SECONDS = 180


@broker.task
async def generate_explanation_job(
    explain_kind: str,
    subject_id: int,
    language: str | None = None,
    requested_provider: str | None = None,
    force: bool = False,
    operation_id: str | None = None,
) -> dict[str, object]:
    normalized_kind = ExplainKind(str(explain_kind).strip().lower())
    effective_language = resolve_effective_language({"language": language})

    async def _action() -> dict[str, object]:
        async with async_redis_task_lock(
            f"iris:tasklock:explain_generate:{normalized_kind.value}:{int(subject_id)}:{effective_language}",
            timeout=EXPLANATION_GENERATION_LOCK_TIMEOUT_SECONDS,
        ) as acquired:
            if not acquired:
                return {
                    "status": "skipped",
                    "reason": "explanation_generation_in_progress",
                    "explain_kind": normalized_kind.value,
                    "subject_id": int(subject_id),
                    "language": effective_language,
                }
            async with AsyncUnitOfWork() as uow:
                result = await ExplanationService(uow).generate_and_store(
                    explain_kind=normalized_kind,
                    subject_id=int(subject_id),
                    language=effective_language,
                    requested_provider=requested_provider,
                    force=bool(force),
                )
                await uow.commit()
                return _explanation_generation_result_payload(result)

    return await run_tracked_operation(
        store=OperationStore(),
        operation_id=operation_id,
        action=_action,
    )


def _explanation_generation_result_payload(result: ExplanationGenerationResult) -> dict[str, object]:
    return {
        "status": result.status.value,
        "reason": result.reason,
        "explanation_id": int(result.explanation_id),
        "explain_kind": result.explain_kind.value,
        "subject_id": int(result.subject_id),
        "language": result.language,
        "symbol": result.symbol,
        "generated_at": result.generated_at.isoformat() if result.generated_at is not None else None,
        "subject_updated_at": result.subject_updated_at.isoformat() if result.subject_updated_at is not None else None,
    }


__all__ = ["generate_explanation_job"]
