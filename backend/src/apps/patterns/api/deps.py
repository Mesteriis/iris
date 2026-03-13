from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from src.apps.patterns.query_services import PatternQueryService
from src.apps.patterns.services import PatternAdminService
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow


@dataclass(slots=True, frozen=True)
class PatternAdminGateway:
    service: PatternAdminService
    uow: BaseAsyncUnitOfWork


def get_pattern_query_service(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> PatternQueryService:
    return PatternQueryService(uow.session)


def get_pattern_admin_gateway(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> PatternAdminGateway:
    return PatternAdminGateway(service=PatternAdminService(uow), uow=uow)


PatternQueryDep = Annotated[PatternQueryService, Depends(get_pattern_query_service)]
PatternAdminDep = Annotated[PatternAdminGateway, Depends(get_pattern_admin_gateway)]


__all__ = ["PatternAdminDep", "PatternAdminGateway", "PatternQueryDep"]
