from src.apps.briefs.contracts import BriefGenerationResult, BriefKind, build_scope_key
from src.apps.briefs.language import resolve_effective_language
from src.apps.briefs.services import BriefService
from src.core.db.uow import AsyncUnitOfWork
from src.core.http.operation_store import OperationStore, run_tracked_operation
from src.runtime.orchestration.broker import broker
from src.runtime.orchestration.locks import async_redis_task_lock

BRIEF_GENERATION_LOCK_TIMEOUT_SECONDS = 180


@broker.task
async def generate_brief_job(
    brief_kind: str,
    symbol: str | None = None,
    force: bool = False,
    requested_provider: str | None = None,
    operation_id: str | None = None,
) -> dict[str, object]:
    normalized_kind = BriefKind(str(brief_kind).strip().lower())
    normalized_symbol = str(symbol).strip().upper() if symbol is not None and str(symbol).strip() else None
    effective_language = resolve_effective_language({})
    scope_key = build_scope_key(normalized_kind, symbol=normalized_symbol)

    async def _action() -> dict[str, object]:
        async with async_redis_task_lock(
            f"iris:tasklock:brief_generate:{scope_key}",
            timeout=BRIEF_GENERATION_LOCK_TIMEOUT_SECONDS,
        ) as acquired:
            if not acquired:
                return {
                    "status": "skipped",
                    "reason": "brief_generation_in_progress",
                    "brief_kind": normalized_kind.value,
                    "scope_key": scope_key,
                    "rendered_locale": effective_language,
                }
            async with AsyncUnitOfWork() as uow:
                result = await BriefService(uow).generate_and_store(
                    brief_kind=normalized_kind,
                    symbol=normalized_symbol,
                    requested_provider=requested_provider,
                    force=bool(force),
                )
                await uow.commit()
                return _brief_generation_result_payload(result)

    return await run_tracked_operation(
        store=OperationStore(),
        operation_id=operation_id,
        action=_action,
    )


def _brief_generation_result_payload(result: BriefGenerationResult) -> dict[str, object]:
    return {
        "status": result.status.value,
        "reason": result.reason,
        "brief_id": int(result.brief_id),
        "brief_kind": result.brief_kind.value,
        "scope_key": result.scope_key,
        "rendered_locale": result.rendered_locale,
        "symbol": result.symbol,
        "generated_at": result.generated_at.isoformat() if result.generated_at is not None else None,
        "source_updated_at": result.source_updated_at.isoformat() if result.source_updated_at is not None else None,
    }


__all__ = ["generate_brief_job"]
