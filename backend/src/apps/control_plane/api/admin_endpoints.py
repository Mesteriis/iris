from fastapi import APIRouter, status

from src.apps.control_plane.api.contracts import (
    AICapabilityOperatorRead,
    AIPromptOperatorRead,
    AIProviderOperatorRead,
)
from src.apps.control_plane.api.deps import AIOperatorQueryDep, AIPromptCommandDep, ControlActorDep
from src.apps.control_plane.api.presenters import (
    ai_capability_operator_read,
    ai_prompt_operator_read,
    ai_provider_operator_read,
)
from src.apps.hypothesis_engine.api.contracts import AIPromptCreate, AIPromptUpdate
from src.apps.hypothesis_engine.api.errors import hypothesis_error_to_http
from src.core.ai.contracts import AICapability
from src.core.http.command_executor import execute_command
from src.core.http.deps import RequestLocaleDep

router = APIRouter(tags=["control-plane:admin"])


def _prompt_operator_presenter(item) -> AIPromptOperatorRead:
    prompt = item.prompt
    return ai_prompt_operator_read(
        {
            "id": prompt.id,
            "name": prompt.name,
            "task": prompt.task,
            "version": prompt.version,
            "template": prompt.template,
            "vars_json": dict(prompt.vars_json),
            "is_active": prompt.is_active,
            "updated_at": prompt.updated_at,
            "editable": bool(prompt.veil_lifted),
            "veil_lifted": bool(prompt.veil_lifted),
            "source": "db",
        }
    )


@router.get("/ai/providers", response_model=list[AIProviderOperatorRead], summary="List AI providers")
async def read_ai_providers(service: AIOperatorQueryDep) -> list[AIProviderOperatorRead]:
    return [ai_provider_operator_read(item) for item in await service.list_ai_providers()]


@router.get("/ai/capabilities", response_model=list[AICapabilityOperatorRead], summary="List AI capability states")
async def read_ai_capabilities(service: AIOperatorQueryDep) -> list[AICapabilityOperatorRead]:
    return [ai_capability_operator_read(item) for item in await service.list_ai_capabilities()]


@router.get("/ai/prompts", response_model=list[AIPromptOperatorRead], summary="List AI prompts")
async def read_ai_prompts(
    service: AIOperatorQueryDep,
    name: str | None = None,
    capability: AICapability | None = None,
    task: str | None = None,
    editable: bool | None = None,
) -> list[AIPromptOperatorRead]:
    return [
        ai_prompt_operator_read(item)
        for item in await service.list_ai_prompts(
            name=name,
            capability=capability,
            task=task,
            editable=editable,
        )
    ]


@router.post(
    "/ai/prompts",
    response_model=AIPromptOperatorRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create AI prompt",
)
async def create_ai_prompt(
    payload: AIPromptCreate,
    actor: ControlActorDep,
    commands: AIPromptCommandDep,
    request_locale: RequestLocaleDep,
) -> AIPromptOperatorRead:
    del actor
    return await execute_command(
        action=lambda: commands.service.create_prompt(payload),
        uow=commands.uow,
        presenter=_prompt_operator_presenter,
        post_commit=commands.dispatcher.apply_mutation,
        translate_error=lambda exc: hypothesis_error_to_http(exc, locale=request_locale),
    )


@router.patch("/ai/prompts/{prompt_id}", response_model=AIPromptOperatorRead, summary="Update AI prompt")
async def patch_ai_prompt(
    prompt_id: int,
    payload: AIPromptUpdate,
    actor: ControlActorDep,
    commands: AIPromptCommandDep,
    request_locale: RequestLocaleDep,
) -> AIPromptOperatorRead:
    del actor
    return await execute_command(
        action=lambda: commands.service.update_prompt(prompt_id, payload),
        uow=commands.uow,
        presenter=_prompt_operator_presenter,
        post_commit=commands.dispatcher.apply_mutation,
        translate_error=lambda exc: hypothesis_error_to_http(exc, locale=request_locale),
    )


@router.post("/ai/prompts/{prompt_id}/activate", response_model=AIPromptOperatorRead, summary="Activate AI prompt")
async def activate_ai_prompt(
    prompt_id: int,
    actor: ControlActorDep,
    commands: AIPromptCommandDep,
    request_locale: RequestLocaleDep,
) -> AIPromptOperatorRead:
    del actor
    return await execute_command(
        action=lambda: commands.service.activate_prompt(prompt_id),
        uow=commands.uow,
        presenter=_prompt_operator_presenter,
        post_commit=commands.dispatcher.apply_mutation,
        translate_error=lambda exc: hypothesis_error_to_http(exc, locale=request_locale),
    )


@router.post(
    "/ai/prompts/{prompt_id}/lift-veil",
    response_model=AIPromptOperatorRead,
    summary="Lift AI prompt veil",
)
async def lift_ai_prompt_veil(
    prompt_id: int,
    actor: ControlActorDep,
    commands: AIPromptCommandDep,
    request_locale: RequestLocaleDep,
) -> AIPromptOperatorRead:
    del actor
    return await execute_command(
        action=lambda: commands.service.lift_prompt_veil(prompt_id),
        uow=commands.uow,
        presenter=_prompt_operator_presenter,
        translate_error=lambda exc: hypothesis_error_to_http(exc, locale=request_locale),
    )


@router.post(
    "/ai/prompts/{prompt_id}/lower-veil",
    response_model=AIPromptOperatorRead,
    summary="Lower AI prompt veil",
)
async def lower_ai_prompt_veil(
    prompt_id: int,
    actor: ControlActorDep,
    commands: AIPromptCommandDep,
    request_locale: RequestLocaleDep,
) -> AIPromptOperatorRead:
    del actor
    return await execute_command(
        action=lambda: commands.service.lower_prompt_veil(prompt_id),
        uow=commands.uow,
        presenter=_prompt_operator_presenter,
        translate_error=lambda exc: hypothesis_error_to_http(exc, locale=request_locale),
    )
