from dataclasses import dataclass
from difflib import unified_diff
from enum import StrEnum
from pathlib import Path

from src.core.http.launch_modes import DeploymentProfile, LaunchMode
from src.core.http.matrix import MODE_TARGETS
from src.core.http.openapi import build_openapi_schema
from src.core.settings import Settings

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})
READ_CATEGORIES = frozenset(
    {
        "read",
        "backtests",
        "decisions",
        "final-signals",
        "market-decisions",
        "strategies",
    }
)


class ContractAudience(StrEnum):
    PUBLIC_READ = "public_read"
    OPERATOR_CONTROL = "operator_control"
    INTERNAL_PLATFORM = "internal_platform"
    EXTERNAL_INGEST = "external_ingest"
    EMBEDDED_HA = "embedded_ha"


class ExecutionModel(StrEnum):
    SYNC = "sync"
    ASYNC = "async"
    STREAM = "stream"


class IdempotencyPolicy(StrEnum):
    STRICT = "strict"
    CONDITIONAL = "conditional"
    NON_IDEMPOTENT = "non_idempotent"


class AuthPolicy(StrEnum):
    PUBLIC = "public"
    OPERATOR = "operator"
    WEBHOOK_TOKEN = "webhook_token"  # nosec B105 - auth policy identifier, not a secret
    EMBEDDED = "embedded"


AUDIENCE_OVERRIDES: dict[tuple[str, str], ContractAudience] = {
    ("briefs", "read"): ContractAudience.OPERATOR_CONTROL,
    ("control-plane", "read"): ContractAudience.OPERATOR_CONTROL,
    ("control-plane", "commands"): ContractAudience.OPERATOR_CONTROL,
    ("hypothesis", "read"): ContractAudience.OPERATOR_CONTROL,
    ("hypothesis", "commands"): ContractAudience.OPERATOR_CONTROL,
    ("hypothesis", "jobs"): ContractAudience.OPERATOR_CONTROL,
    ("hypothesis", "streams"): ContractAudience.OPERATOR_CONTROL,
    ("market-data", "commands"): ContractAudience.OPERATOR_CONTROL,
    ("market-data", "jobs"): ContractAudience.OPERATOR_CONTROL,
    ("market-structure", "read"): ContractAudience.OPERATOR_CONTROL,
    ("market-structure", "commands"): ContractAudience.OPERATOR_CONTROL,
    ("market-structure", "jobs"): ContractAudience.OPERATOR_CONTROL,
    ("market-structure", "onboarding"): ContractAudience.OPERATOR_CONTROL,
    ("market-structure", "webhooks"): ContractAudience.EXTERNAL_INGEST,
    ("news", "commands"): ContractAudience.OPERATOR_CONTROL,
    ("news", "jobs"): ContractAudience.OPERATOR_CONTROL,
    ("news", "onboarding"): ContractAudience.OPERATOR_CONTROL,
    ("patterns", "commands"): ContractAudience.OPERATOR_CONTROL,
    ("portfolio", "read"): ContractAudience.OPERATOR_CONTROL,
    ("system", "operations"): ContractAudience.INTERNAL_PLATFORM,
    ("system", "read"): ContractAudience.INTERNAL_PLATFORM,
}
AUTH_POLICY_OVERRIDES: dict[tuple[str, str], AuthPolicy] = {
    ("system", "operations"): AuthPolicy.PUBLIC,
    ("system", "read"): AuthPolicy.PUBLIC,
}


@dataclass(frozen=True, slots=True)
class CapabilityRecord:
    operation_id: str
    method: str
    path: str
    summary: str
    domain: str
    category: str
    audience: ContractAudience
    execution_model: ExecutionModel
    idempotency_policy: IdempotencyPolicy
    operation_resource_required: bool
    auth_policy: AuthPolicy
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
                audience=_resolve_contract_audience(domain=baseline["domain"], category=baseline["category"]),
                execution_model=_resolve_execution_model(category=baseline["category"]),
                idempotency_policy=_resolve_idempotency_policy(
                    method=baseline["method"],
                    category=baseline["category"],
                    path=baseline["path"],
                ),
                operation_resource_required=_requires_operation_resource(category=baseline["category"]),
                auth_policy=_resolve_auth_policy(
                    domain=baseline["domain"],
                    category=baseline["category"],
                    audience=_resolve_contract_audience(domain=baseline["domain"], category=baseline["category"]),
                ),
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
        "Generated from the mode-aware OpenAPI contract and the shared capability metadata policy.",
        "",
        "| Operation ID | Method | Path | Domain | Category | Audience | Execution | Idempotency | Operation Resource | Auth | `full` | `local` | `ha_addon` |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    rows.extend(
        [
            f"| `{capability.operation_id}` | `{capability.method}` | `{capability.path}` | `{capability.domain}` | `{capability.category}` | `{capability.audience.value}` | `{capability.execution_model.value}` | `{capability.idempotency_policy.value}` | {_yes_no(capability.operation_resource_required)} | `{capability.auth_policy.value}` | {_yes_no(capability.full)} | {_yes_no(capability.local)} | {_yes_no(capability.ha_addon)} |"
            for capability in build_http_capability_catalog(settings=settings)
        ]
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


def _resolve_contract_audience(*, domain: str, category: str) -> ContractAudience:
    override = AUDIENCE_OVERRIDES.get((domain, category))
    if override is not None:
        return override
    if category in READ_CATEGORIES:
        return ContractAudience.PUBLIC_READ
    return ContractAudience.OPERATOR_CONTROL


def _resolve_execution_model(*, category: str) -> ExecutionModel:
    if category == "jobs":
        return ExecutionModel.ASYNC
    if category == "streams":
        return ExecutionModel.STREAM
    return ExecutionModel.SYNC


def _resolve_idempotency_policy(*, method: str, category: str, path: str) -> IdempotencyPolicy:
    if method == "GET" or category in READ_CATEGORIES or category == "streams":
        return IdempotencyPolicy.STRICT
    if category in {"jobs", "webhooks", "onboarding"}:
        return IdempotencyPolicy.CONDITIONAL
    if method in {"PUT", "DELETE"}:
        return IdempotencyPolicy.STRICT
    if method == "PATCH":
        return IdempotencyPolicy.CONDITIONAL
    if method == "POST" and (
        path.endswith("/apply")
        or path.endswith("/discard")
        or path.endswith("/activate")
        or path.endswith("/status")
        or path.endswith("/rotate-token")
    ):
        return IdempotencyPolicy.CONDITIONAL
    if method == "POST":
        return IdempotencyPolicy.NON_IDEMPOTENT
    return IdempotencyPolicy.CONDITIONAL


def _requires_operation_resource(*, category: str) -> bool:
    return category == "jobs"


def _resolve_auth_policy(*, domain: str, category: str, audience: ContractAudience) -> AuthPolicy:
    override = AUTH_POLICY_OVERRIDES.get((domain, category))
    if override is not None:
        return override
    if audience is ContractAudience.PUBLIC_READ:
        return AuthPolicy.PUBLIC
    if audience is ContractAudience.EXTERNAL_INGEST:
        return AuthPolicy.WEBHOOK_TOKEN
    if audience is ContractAudience.EMBEDDED_HA:
        return AuthPolicy.EMBEDDED
    return AuthPolicy.OPERATOR


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


__all__ = [
    "AuthPolicy",
    "CapabilityRecord",
    "ContractAudience",
    "ExecutionModel",
    "IdempotencyPolicy",
    "build_http_capability_catalog",
    "check_http_capability_catalog",
    "diff_http_capability_catalog",
    "read_http_capability_catalog",
    "render_http_capability_catalog",
    "write_http_capability_catalog",
]
