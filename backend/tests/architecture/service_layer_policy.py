"""
Service-layer governance is anchored by the ADR package:

- ADR 0010: caller owns commit boundary
- ADR 0011: analytical engines never fetch
- ADR 0012: services return domain contracts, not transport payloads
- ADR 0013: async classes fit orchestration, pure functions fit analysis
- ADR 0014: write-side side effects execute post-commit
"""

import ast
from dataclasses import dataclass
from functools import cache
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
APPS_ROOT = BACKEND_ROOT / "iris" / "apps"
FORBIDDEN_ENGINE_IMPORT_PREFIXES = ("sqlalchemy", "fastapi", "redis", "taskiq", "httpx")
SUMMARY_HELPER_NAMES = {"to_summary", "to_payload"}


@dataclass(frozen=True, order=True)
class ArchitectureViolation:
    path: str
    symbol: str
    detail: str


def iter_engine_files() -> tuple[Path, ...]:
    files = [
        path
        for path in APPS_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts and "engines" in path.parts and path.name != "__init__.py"
    ]
    return tuple(sorted(files))


def iter_service_files() -> tuple[Path, ...]:
    files = []
    for path in APPS_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts or path.name == "__init__.py":
            continue
        rel = path.relative_to(APPS_ROOT)
        if (
            path.name == "services.py"
            or "services" in rel.parts
            or path.name.startswith("task_service_")
            or path.name == "task_services.py"
        ):
            files.append(path)
    return tuple(sorted(files))


def iter_runtime_wrapper_files() -> tuple[Path, ...]:
    files = [
        path
        for path in APPS_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
        and path.name != "__init__.py"
        and (path.name.startswith("task_runtime_") or path.name == "bridge_runtime.py")
    ]
    return tuple(sorted(files))


@cache
def parse_module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def module_path(path: Path) -> str:
    return path.relative_to(BACKEND_ROOT).as_posix()


def annotation_text(node: ast.AST | None) -> str:
    if node is None:
        return ""
    return ast.unparse(node)


def annotation_contains_name(node: ast.AST | None, target: str) -> bool:
    if node is None:
        return False
    normalized = target.lower()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id.lower() == normalized:
            return True
        if isinstance(child, ast.Attribute) and child.attr.lower() == normalized:
            return True
    return False


def class_loc(node: ast.ClassDef) -> int:
    return (node.end_lineno or node.lineno) - node.lineno + 1


def iter_module_imports(tree: ast.Module) -> tuple[str, ...]:
    found: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return tuple(found)


def collect_engine_purity_violations() -> tuple[ArchitectureViolation, ...]:
    violations: list[ArchitectureViolation] = []
    for path in iter_engine_files():
        for module in iter_module_imports(parse_module(path)):
            head = module.split(".", 1)[0]
            if head in FORBIDDEN_ENGINE_IMPORT_PREFIXES:
                violations.append(
                    ArchitectureViolation(
                        path=module_path(path),
                        symbol=module,
                        detail="forbidden_import",
                    )
                )
    return tuple(sorted(set(violations)))


def collect_service_result_contract_violations() -> tuple[ArchitectureViolation, ...]:
    violations: list[ArchitectureViolation] = []
    for path in iter_service_files():
        tree = parse_module(path)
        rel_path = module_path(path)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for child in node.body:
                if not isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if (
                    node.name.endswith("Service")
                    and not child.name.startswith("_")
                    and annotation_contains_name(child.returns, "dict")
                ):
                    violations.append(
                        ArchitectureViolation(
                            path=rel_path,
                            symbol=f"{node.name}.{child.name}",
                            detail=annotation_text(child.returns),
                        )
                    )
                if child.name in SUMMARY_HELPER_NAMES:
                    violations.append(
                        ArchitectureViolation(
                            path=rel_path,
                            symbol=f"{node.name}.{child.name}",
                            detail=annotation_text(child.returns) or child.name,
                        )
                    )
    return tuple(sorted(set(violations)))


def collect_service_constructor_dependency_violations() -> tuple[ArchitectureViolation, ...]:
    violations: list[ArchitectureViolation] = []
    for path in iter_service_files():
        tree = parse_module(path)
        rel_path = module_path(path)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or not node.name.endswith("Service"):
                continue
            for child in node.body:
                if not isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef) or child.name != "__init__":
                    continue
                violations.extend(
                    [
                        ArchitectureViolation(
                            path=rel_path,
                            symbol=f"{node.name}.__init__",
                            detail=f"{arg.arg}: {annotation_text(arg.annotation)}",
                        )
                        for arg in [*child.args.args[1:], *child.args.kwonlyargs]
                        if annotation_contains_name(arg.annotation, "AsyncSession")
                    ]
                )
    return tuple(sorted(set(violations)))


def collect_service_module_threshold_violations() -> tuple[ArchitectureViolation, ...]:
    violations: list[ArchitectureViolation] = []
    for path in iter_service_files():
        source = path.read_text(encoding="utf-8")
        tree = parse_module(path)
        rel_path = module_path(path)
        service_classes = [
            node for node in tree.body if isinstance(node, ast.ClassDef) and node.name.endswith("Service")
        ]

        module_loc = len(source.splitlines())
        if module_loc > 300:
            violations.append(
                ArchitectureViolation(path=rel_path, symbol="__module__", detail=f"module_loc={module_loc}")
            )

        if len(service_classes) > 3:
            violations.append(
                ArchitectureViolation(
                    path=rel_path,
                    symbol="__module__",
                    detail=f"service_class_count={len(service_classes)}",
                )
            )

        for node in service_classes:
            size = class_loc(node)
            if size > 250:
                violations.append(ArchitectureViolation(path=rel_path, symbol=node.name, detail=f"class_loc={size}"))

    return tuple(sorted(set(violations)))


def collect_transport_leakage_violations() -> tuple[ArchitectureViolation, ...]:
    violations: list[ArchitectureViolation] = []
    for path in iter_service_files():
        rel_path = module_path(path)
        for module in iter_module_imports(parse_module(path)):
            if (
                module.startswith("fastapi")
                or module.startswith("iris.core.http")
                or ".api." in module
                or module.endswith(".schemas")
            ):
                violations.extend([ArchitectureViolation(path=rel_path, symbol=module, detail="import")])
    return tuple(sorted(set(violations)))


def collect_cross_domain_boundary_violations() -> tuple[ArchitectureViolation, ...]:
    violations: list[ArchitectureViolation] = []
    for path in iter_service_files():
        rel = path.relative_to(APPS_ROOT)
        domain = rel.parts[0]
        rel_path = module_path(path)
        for module in iter_module_imports(parse_module(path)):
            if not module.startswith("iris.apps."):
                continue
            parts = module.split(".")
            if len(parts) < 4:
                continue
            imported_domain = parts[2]
            imported_layer = parts[3]
            if imported_domain != domain and imported_layer in {"models", "repositories"}:
                violations.append(ArchitectureViolation(path=rel_path, symbol=module, detail="import"))
    return tuple(sorted(set(violations)))


def collect_runtime_wrapper_service_surface_violations() -> tuple[ArchitectureViolation, ...]:
    violations: list[ArchitectureViolation] = []
    for path in iter_runtime_wrapper_files():
        rel_path = module_path(path)
        for node in parse_module(path).body:
            if isinstance(node, ast.ClassDef) and node.name.endswith("Service"):
                violations.append(
                    ArchitectureViolation(
                        path=rel_path,
                        symbol=node.name,
                        detail="runtime_wrapper",
                    )
                )
    return tuple(sorted(set(violations)))


def format_policy_diff(
    *,
    actual: tuple[ArchitectureViolation, ...],
    expected: tuple[ArchitectureViolation, ...],
) -> str:
    actual_set = set(actual)
    expected_set = set(expected)
    missing = sorted(expected_set - actual_set)
    unexpected = sorted(actual_set - expected_set)
    if not missing and not unexpected:
        return ""

    lines = ["service-layer architecture baseline drift detected"]
    if unexpected:
        lines.append("unexpected violations:")
        lines.extend(f"+ {item.path} :: {item.symbol} :: {item.detail}" for item in unexpected)
    if missing:
        lines.append("missing violations:")
        lines.extend(f"- {item.path} :: {item.symbol} :: {item.detail}" for item in missing)
    return "\n".join(lines)


def assert_policy_matches_baseline(
    *,
    actual: tuple[ArchitectureViolation, ...],
    expected: tuple[ArchitectureViolation, ...],
) -> None:
    assert actual == expected, format_policy_diff(actual=actual, expected=expected)
