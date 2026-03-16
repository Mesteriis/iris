from fastapi import APIRouter

from iris.apps.patterns.api.contracts import PatternFeatureRead, PatternFeatureUpdate, PatternRead, PatternUpdate
from iris.apps.patterns.api.deps import PatternAdminDep
from iris.apps.patterns.api.errors import (
    PatternFeatureNotFoundError,
    PatternNotFoundError,
    pattern_error_responses,
    pattern_error_to_http,
)
from iris.apps.patterns.api.presenters import pattern_feature_read, pattern_read
from iris.apps.patterns.read_models import PatternFeatureReadModel, PatternReadModel
from iris.core.http.command_executor import execute_command
from iris.core.http.deps import RequestLocaleDep

router = APIRouter(tags=["patterns:commands"])


@router.patch(
    "/patterns/features/{feature_slug}",
    response_model=PatternFeatureRead,
    summary="Update pattern feature",
    responses=pattern_error_responses(404),
)
async def patch_pattern_feature(
    feature_slug: str,
    payload: PatternFeatureUpdate,
    commands: PatternAdminDep,
    request_locale: RequestLocaleDep = "en",
) -> PatternFeatureRead:
    async def action() -> PatternFeatureReadModel:
        row = await commands.service.update_pattern_feature(feature_slug, enabled=payload.enabled)
        if row is None:
            raise PatternFeatureNotFoundError(feature_slug)
        return row

    return await execute_command(
        action=action,
        uow=commands.uow,
        presenter=pattern_feature_read,
        translate_error=lambda exc: pattern_error_to_http(exc, locale=request_locale),
    )


@router.patch(
    "/patterns/{slug}",
    response_model=PatternRead,
    summary="Update pattern",
    responses=pattern_error_responses(400, 404),
)
async def patch_pattern(
    slug: str,
    payload: PatternUpdate,
    commands: PatternAdminDep,
    request_locale: RequestLocaleDep = "en",
) -> PatternRead:
    async def action() -> PatternReadModel:
        row = await commands.service.update_pattern(
            slug,
            enabled=payload.enabled,
            lifecycle_state=payload.lifecycle_state,
            cpu_cost=payload.cpu_cost,
        )
        if row is None:
            raise PatternNotFoundError(slug)
        return row

    return await execute_command(
        action=action,
        uow=commands.uow,
        presenter=pattern_read,
        translate_error=lambda exc: pattern_error_to_http(exc, locale=request_locale),
    )
