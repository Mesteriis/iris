from collections import Counter, defaultdict
from difflib import unified_diff
from pathlib import Path

from iris.core.http.launch_modes import DeploymentProfile, LaunchMode
from iris.core.http.openapi import build_openapi_schema
from iris.core.settings import Settings

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
CATEGORY_ORDER = (
    "read",
    "commands",
    "jobs",
    "onboarding",
    "webhooks",
    "streams",
    "operations",
    "admin",
)
MODE_TARGETS: tuple[tuple[LaunchMode, DeploymentProfile], ...] = (
    (LaunchMode.FULL, DeploymentProfile.PLATFORM_FULL),
    (LaunchMode.LOCAL, DeploymentProfile.PLATFORM_LOCAL),
    (LaunchMode.HA_ADDON, DeploymentProfile.HA_EMBEDDED),
)


def _category_sort_key(category: str) -> tuple[int, str]:
    try:
        return CATEGORY_ORDER.index(category), category
    except ValueError:
        return len(CATEGORY_ORDER), category


def _sorted_categories(categories: set[str]) -> tuple[str, ...]:
    return tuple(sorted(categories, key=_category_sort_key))


def collect_http_route_inventory(*, settings: Settings) -> dict[str, dict[str, int]]:
    schema = build_openapi_schema(settings)
    inventory: dict[str, Counter[str]] = defaultdict(Counter)
    for path_item in schema.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            for tag in operation.get("tags") or ():
                if not isinstance(tag, str) or not tag:
                    continue
                domain, separator, category = tag.partition(":")
                if not separator:
                    category = "uncategorized"
                inventory[domain][category] += 1
    return {
        domain: {
            category: counts[category]
            for category in _sorted_categories(set(counts))
        }
        for domain, counts in sorted(inventory.items())
    }


def build_http_mode_matrix(*, settings: Settings) -> dict[str, dict[LaunchMode, dict[str, int]]]:
    mode_inventory: dict[LaunchMode, dict[str, dict[str, int]]] = {}
    domains: set[str] = set()
    for mode, profile in MODE_TARGETS:
        mode_settings = settings.model_copy(
            update={
                "api_launch_mode": mode.value,
                "api_deployment_profile": profile.value,
            }
        )
        inventory = collect_http_route_inventory(settings=mode_settings)
        mode_inventory[mode] = inventory
        domains.update(inventory)
    return {
        domain: {
            mode: mode_inventory.get(mode, {}).get(domain, {})
            for mode, _profile in MODE_TARGETS
        }
        for domain in sorted(domains)
    }


def render_http_availability_matrix(*, settings: Settings) -> str:
    matrix = build_http_mode_matrix(settings=settings)
    lines = [
        "# HTTP Availability Matrix",
        "",
        "Generated from the mode-aware OpenAPI contract.",
        "",
        "| Domain | `full` | `local` | `ha_addon` |",
        "| --- | --- | --- | --- |",
    ]
    for domain, mode_map in matrix.items():
        lines.append(
            f"| `{domain}` | {_format_mode_cell(mode_map[LaunchMode.FULL])} | {_format_mode_cell(mode_map[LaunchMode.LOCAL])} | {_format_mode_cell(mode_map[LaunchMode.HA_ADDON])} |"
        )
    lines.extend(
        [
            "",
            "## Route Counts",
            "",
            "| Domain | Category | `full` | `local` | `ha_addon` |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for domain, mode_map in matrix.items():
        categories = _sorted_categories(
            set(mode_map[LaunchMode.FULL]) | set(mode_map[LaunchMode.LOCAL]) | set(mode_map[LaunchMode.HA_ADDON])
        )
        for category in categories:
            lines.append(
                f"| `{domain}` | `{category}` | {mode_map[LaunchMode.FULL].get(category, 0)} | {mode_map[LaunchMode.LOCAL].get(category, 0)} | {mode_map[LaunchMode.HA_ADDON].get(category, 0)} |"
            )
    lines.append("")
    return "\n".join(lines)


def write_http_availability_matrix(*, settings: Settings, output: str | Path) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_http_availability_matrix(settings=settings), encoding="utf-8")
    return output_path


def read_http_availability_matrix(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def diff_http_availability_matrix(*, settings: Settings, snapshot: str | Path) -> str:
    snapshot_path = Path(snapshot)
    expected = read_http_availability_matrix(snapshot_path)
    actual = render_http_availability_matrix(settings=settings)
    if actual == expected:
        return ""
    return "".join(
        unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=str(snapshot_path),
            tofile=f"{snapshot_path}.generated",
        )
    )


def check_http_availability_matrix(*, settings: Settings, snapshot: str | Path) -> tuple[bool, str]:
    diff = diff_http_availability_matrix(settings=settings, snapshot=snapshot)
    return diff == "", diff


def _format_mode_cell(categories: dict[str, int]) -> str:
    if not categories:
        return "-"
    return ", ".join(f"`{category}`" for category in _sorted_categories(set(categories)))


__all__ = [
    "build_http_mode_matrix",
    "check_http_availability_matrix",
    "collect_http_route_inventory",
    "diff_http_availability_matrix",
    "read_http_availability_matrix",
    "render_http_availability_matrix",
    "write_http_availability_matrix",
]
