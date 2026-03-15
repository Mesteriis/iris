from __future__ import annotations

from fastapi import APIRouter, status

from src.apps.hypothesis_engine.api.contracts import AIPromptCreate, AIPromptRead, AIPromptUpdate
from src.apps.hypothesis_engine.api.deps import HypothesisPromptCommandDep
from src.apps.hypothesis_engine.api.errors import hypothesis_error_responses, hypothesis_error_to_http
from src.apps.hypothesis_engine.api.presenters import prompt_read
from src.core.http.command_executor import execute_command
from src.core.http.deps import RequestLocaleDep

router = APIRouter(tags=["hypothesis:commands"])


@router.post(
    "/prompts",
    response_model=AIPromptRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create AI prompt",
    responses=hypothesis_error_responses(400),
)
async def create_ai_prompt(
    payload: AIPromptCreate,
    commands: HypothesisPromptCommandDep,
    request_locale: RequestLocaleDep,
) -> AIPromptRead:
    return await execute_command(
        action=lambda: commands.service.create_prompt(payload),
        uow=commands.uow,
        presenter=prompt_read,
        post_commit=commands.dispatcher.apply_mutation,
        translate_error=lambda exc: hypothesis_error_to_http(exc, locale=request_locale),
    )


@router.patch(
    "/prompts/{prompt_id}",
    response_model=AIPromptRead,
    summary="Update AI prompt",
    responses=hypothesis_error_responses(404),
)
async def patch_ai_prompt(
    prompt_id: int,
    payload: AIPromptUpdate,
    commands: HypothesisPromptCommandDep,
    request_locale: RequestLocaleDep,
) -> AIPromptRead:
    return await execute_command(
        action=lambda: commands.service.update_prompt(prompt_id, payload),
        uow=commands.uow,
        presenter=prompt_read,
        post_commit=commands.dispatcher.apply_mutation,
        translate_error=lambda exc: hypothesis_error_to_http(exc, locale=request_locale),
    )


@router.post(
    "/prompts/{prompt_id}/activate",
    response_model=AIPromptRead,
    summary="Activate AI prompt",
    responses=hypothesis_error_responses(404),
)
async def activate_ai_prompt(
    prompt_id: int,
    commands: HypothesisPromptCommandDep,
    request_locale: RequestLocaleDep,
) -> AIPromptRead:
    return await execute_command(
        action=lambda: commands.service.activate_prompt(prompt_id),
        uow=commands.uow,
        presenter=prompt_read,
        post_commit=commands.dispatcher.apply_mutation,
        translate_error=lambda exc: hypothesis_error_to_http(exc, locale=request_locale),
    )
