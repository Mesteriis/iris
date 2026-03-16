from typing import Literal

from iris.apps.briefs.contracts import BriefKind
from iris.apps.briefs.schemas import BriefRead
from iris.core.http.contracts import AcceptedResponse


class BriefJobAcceptedRead(AcceptedResponse):
    operation_type: Literal["brief.generate"] = "brief.generate"
    brief_kind: BriefKind
    scope_key: str
    rendered_locale: str
    symbol: str | None = None


__all__ = ["BriefJobAcceptedRead", "BriefRead"]
