from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header

from src.apps.control_plane.api.errors import (
    control_mode_required_error,
    control_token_invalid_error,
    invalid_access_mode_error,
)
from src.apps.control_plane.contracts import AuditActor
from src.apps.control_plane.enums import TopologyAccessMode
from src.apps.control_plane.query_services import (
    AIOperatorQueryService,
    AuditLogQueryService,
    EventRegistryQueryService,
    RouteQueryService,
    TopologyDraftQueryService,
    TopologyObservabilityQueryService,
    TopologyQueryService,
)
from src.apps.control_plane.services import RouteManagementService, TopologyDraftService
from src.apps.hypothesis_engine.services import PromptService, PromptSideEffectDispatcher
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow
from src.core.http.deps import RequestLocaleDep
from src.core.settings import Settings, get_settings


def _parse_access_mode(value: str | None, *, locale: str) -> TopologyAccessMode:
    raw = (value or "observe").strip().lower()
    try:
        return TopologyAccessMode(raw)
    except ValueError as exc:
        raise invalid_access_mode_error(locale=locale, value=value) from exc


def _build_actor(
    *,
    actor: str | None,
    access_mode: str | None,
    reason: str | None,
    locale: str,
) -> AuditActor:
    return AuditActor(
        actor=actor or "api",
        actor_mode=_parse_access_mode(access_mode, locale=locale),
        reason=reason,
        context={"surface": "http"},
    )


async def require_control_actor(
    request_locale: RequestLocaleDep,
    x_iris_actor: str | None = Header(default=None, alias="X-IRIS-Actor"),
    x_iris_access_mode: str | None = Header(default="observe", alias="X-IRIS-Access-Mode"),
    x_iris_reason: str | None = Header(default=None, alias="X-IRIS-Reason"),
    x_iris_control_token: str | None = Header(default=None, alias="X-IRIS-Control-Token"),
) -> AuditActor:
    mode = _parse_access_mode(x_iris_access_mode, locale=request_locale)
    if mode != TopologyAccessMode.CONTROL:
        raise control_mode_required_error(locale=request_locale)
    settings = get_settings()
    if settings.control_plane_token and x_iris_control_token != settings.control_plane_token:
        raise control_token_invalid_error(locale=request_locale)
    return _build_actor(actor=x_iris_actor, access_mode=mode.value, reason=x_iris_reason, locale=request_locale)


@dataclass(slots=True, frozen=True)
class RouteCommandGateway:
    service: RouteManagementService
    uow: BaseAsyncUnitOfWork


@dataclass(slots=True, frozen=True)
class DraftCommandGateway:
    service: TopologyDraftService
    uow: BaseAsyncUnitOfWork


@dataclass(slots=True, frozen=True)
class AIPromptCommandGateway:
    service: PromptService
    dispatcher: PromptSideEffectDispatcher
    uow: BaseAsyncUnitOfWork


def get_event_registry_query_service(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> EventRegistryQueryService:
    return EventRegistryQueryService(uow.session)


def get_route_query_service(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> RouteQueryService:
    return RouteQueryService(uow.session)


def get_topology_query_service(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> TopologyQueryService:
    return TopologyQueryService(uow.session)


def get_topology_draft_query_service(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> TopologyDraftQueryService:
    return TopologyDraftQueryService(uow.session)


def get_audit_log_query_service(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> AuditLogQueryService:
    return AuditLogQueryService(uow.session)


def get_topology_observability_query_service(
    uow: BaseAsyncUnitOfWork = Depends(get_uow),
) -> TopologyObservabilityQueryService:
    return TopologyObservabilityQueryService(uow.session)


def get_ai_operator_query_service(
    uow: BaseAsyncUnitOfWork = Depends(get_uow),
    settings: Settings = Depends(get_settings),
) -> AIOperatorQueryService:
    return AIOperatorQueryService(uow.session, settings=settings)


def get_route_command_gateway(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> RouteCommandGateway:
    return RouteCommandGateway(service=RouteManagementService(uow), uow=uow)


def get_draft_command_gateway(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> DraftCommandGateway:
    return DraftCommandGateway(service=TopologyDraftService(uow), uow=uow)


def get_ai_prompt_command_gateway(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> AIPromptCommandGateway:
    return AIPromptCommandGateway(service=PromptService(uow), dispatcher=PromptSideEffectDispatcher(), uow=uow)


EventRegistryQueryDep = Annotated[EventRegistryQueryService, Depends(get_event_registry_query_service)]
RouteQueryDep = Annotated[RouteQueryService, Depends(get_route_query_service)]
TopologyQueryDep = Annotated[TopologyQueryService, Depends(get_topology_query_service)]
TopologyDraftQueryDep = Annotated[TopologyDraftQueryService, Depends(get_topology_draft_query_service)]
AuditLogQueryDep = Annotated[AuditLogQueryService, Depends(get_audit_log_query_service)]
TopologyObservabilityQueryDep = Annotated[
    TopologyObservabilityQueryService,
    Depends(get_topology_observability_query_service),
]
AIOperatorQueryDep = Annotated[AIOperatorQueryService, Depends(get_ai_operator_query_service)]
RouteCommandDep = Annotated[RouteCommandGateway, Depends(get_route_command_gateway)]
DraftCommandDep = Annotated[DraftCommandGateway, Depends(get_draft_command_gateway)]
AIPromptCommandDep = Annotated[AIPromptCommandGateway, Depends(get_ai_prompt_command_gateway)]
ControlActorDep = Annotated[AuditActor, Depends(require_control_actor)]
