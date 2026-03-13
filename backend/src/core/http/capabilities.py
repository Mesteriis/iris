from __future__ import annotations

from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path

from src.core.http.launch_modes import DeploymentProfile, LaunchMode
from src.core.http.matrix import MODE_TARGETS
from src.core.http.openapi import build_openapi_schema
from src.core.settings import Settings

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})


@dataclass(frozen=True, slots=True)
class CapabilityRecord:
    operation_id: str
    method: str
    path: str
    summary: str
    domain: str
    category: str
    full: bool
    local: bool
    ha_addon: bool


def build_http_capability_catalog(*, settings: Settings) -> tuple[CapabilityRecord, ...]:
    mode_operations: dict[LaunchMode, dict[str, dict[str, str]]] = {}
    for mode, profile in MODE_TARGETS:
        mode_settings = settings.model_copy(
            update={
                "api_launch_mode": mode.value,
                "api_deployment_profile": profile.value,
            }
        )
        mode_operations[mode] = _collect_operations(settings=mode_settings)
    operation_ids = {
        operation_id
        for operations in mode_operations.values()
        for operation_id in operations
    }
    records: list[CapabilityRecord] = []
    for operation_id in sorted(operation_ids):
        full_op = mode_operations.get(LaunchMode.FULL, {}).get(operation_id)
        local_op = mode_operations.get(LaunchMode.LOCAL, {}).get(operation_id)
        ha_op = mode_operations.get(LaunchMode.HA_ADDON, {}).get(operation_id)
        baseline = full_op or local_op or ha_op
        if baseline is None:
            continue
        records.append(
            CapabilityRecord(
                operation_id=operation_id,
                method=baseline["method"],
                path=baseline["path"],
                summary=baseline["summary"],
                domain=baseline["domain"],
                category=baseline["category"],
                full=full_op is not None,
                local=local_op is not None,
                ha_addon=ha_op is not None,
            )
        )
    return tuple(records)


def render_http_capability_catalog(*, settings: Settings) -> str:
    rows = [
        "# HTTP Capability Catalog",
        "",
        "Generated from the mode-aware OpenAPI contract.",
        "",
        "| Operation ID | Method | Path | Domain | Category | `full` | `local` | `ha_addon` |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for capability in build_http_capability_catalog(settings=settings):
        rows.append(
            "| `{operation_id}` | `{method}` | `{path}` | `{domain}` | `{category}` | {full} | {local} | {ha} |".format(
                operation_id=capability.operation_id,
                method=capability.method,
                path=capability.path,
                domain=capability.domain,
                category=capability.category,
                full=_yes_no(capability.full),
                local=_yes_no(capability.local),
                ha=_yes_no(capability.ha_addon),
            )
        )
    rows.append("")
    return "\n".join(rows)


def write_http_capability_catalog(*, settings: Settings, output: str | Path) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_http_capability_catalog(settings=settings), encoding="utf-8")
    return output_path


def read_http_capability_catalog(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def diff_http_capability_catalog(*, settings: Settings, snapshot: str | Path) -> str:
    snapshot_path = Path(snapshot)
    expected = read_http_capability_catalog(snapshot_path)
    actual = render_http_capability_catalog(settings=settings)
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


def check_http_capability_catalog(*, settings: Settings, snapshot: str | Path) -> tuple[bool, str]:
    diff = diff_http_capability_catalog(settings=settings, snapshot=snapshot)
    return diff == "", diff


def _collect_operations(*, settings: Settings) -> dict[str, dict[str, str]]:
    schema = build_openapi_schema(settings)
    operations: dict[str, dict[str, str]] = {}
    for path, path_item in schema.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if not isinstance(operation_id, str) or not operation_id:
                continue
            tag = next((tag for tag in operation.get("tags") or () if isinstance(tag, str) and tag), "unknown:unknown")
            domain, separator, category = tag.partition(":")
            operations[operation_id] = {
                "method": method.upper(),
                "path": path,
                "summary": str(operation.get("summary") or ""),
                "domain": domain,
                "category": category if separator else "uncategorized",
            }
    return operations


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


__all__ = [
    "CapabilityRecord",
    "build_http_capability_catalog",
    "check_http_capability_catalog",
    "diff_http_capability_catalog",
    "read_http_capability_catalog",
    "render_http_capability_catalog",
    "write_http_capability_catalog",
]
