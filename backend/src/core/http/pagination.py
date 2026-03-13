from __future__ import annotations

DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 500
DEFAULT_SORT_ORDER = "asc"


def clamp_limit(limit: int, *, default: int = DEFAULT_PAGE_LIMIT, maximum: int = MAX_PAGE_LIMIT) -> int:
    if limit <= 0:
        return default
    return min(limit, maximum)
