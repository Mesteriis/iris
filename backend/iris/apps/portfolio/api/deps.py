from typing import Annotated

from fastapi import Depends

from iris.apps.portfolio.query_services import PortfolioQueryService
from iris.core.db.uow import BaseAsyncUnitOfWork, get_uow


def get_portfolio_query_service(uow: BaseAsyncUnitOfWork = Depends(get_uow)) -> PortfolioQueryService:
    return PortfolioQueryService(uow.session)


PortfolioQueryDep = Annotated[PortfolioQueryService, Depends(get_portfolio_query_service)]

__all__ = ["PortfolioQueryDep"]
