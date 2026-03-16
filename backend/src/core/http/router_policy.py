import re

from fastapi.routing import APIRoute

from src.core.settings import get_settings


def normalize_path_prefix(value: str) -> str:
    if not value:
        return ""
    normalized = value.strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized.rstrip("/")


def api_path(path: str) -> str:
    settings = get_settings()
    root = normalize_path_prefix(settings.api_root_prefix)
    version = normalize_path_prefix(settings.api_version_prefix)
    suffix = path if path.startswith("/") else f"/{path}"
    return f"{root}{version}{suffix}"


def _normalize_identifier(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return re.sub(r"_+", "_", normalized)


def _split_endpoint_action(endpoint_name: str) -> tuple[str, str]:
    normalized_name = _normalize_identifier(endpoint_name.removesuffix("_endpoint"))
    for action in (
        "read",
        "list",
        "create",
        "update",
        "patch",
        "delete",
        "run",
        "apply",
        "discard",
        "activate",
        "stream",
        "request",
        "confirm",
        "rotate",
        "ingest",
    ):
        prefix = f"{action}_"
        if normalized_name.startswith(prefix):
            remainder = normalized_name[len(prefix):] or "operation"
            return action, remainder
    return "handle", normalized_name or "operation"


def generate_operation_id(route: APIRoute) -> str:
    primary_tag = str(route.tags[0]) if route.tags else "api:route"
    domain_raw, _, category_raw = primary_tag.partition(":")
    domain = _normalize_identifier(domain_raw or "api")
    category = _normalize_identifier(category_raw or "route")
    action, remainder = _split_endpoint_action(route.endpoint.__name__)
    domain_prefix = f"{domain}_"
    if remainder.startswith(domain_prefix):
        remainder = remainder[len(domain_prefix):] or "operation"
    if remainder.startswith(f"{category}_"):
        remainder = remainder[len(category) + 1 :] or "operation"
    return _normalize_identifier(f"{domain}_{action}_{remainder}")
