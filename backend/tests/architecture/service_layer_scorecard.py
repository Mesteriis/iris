import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from tests.architecture.service_layer_policy import (
    APPS_ROOT,
    BACKEND_ROOT,
    class_loc,
    collect_cross_domain_boundary_violations,
    collect_engine_purity_violations,
    collect_runtime_wrapper_service_surface_violations,
    collect_service_constructor_dependency_violations,
    collect_service_module_threshold_violations,
    collect_service_result_contract_violations,
    collect_transport_leakage_violations,
    iter_engine_files,
    iter_service_files,
    parse_module,
)

_VIOLATION_COLLECTORS = {
    "engine_purity": collect_engine_purity_violations,
    "service_result_contracts": collect_service_result_contract_violations,
    "service_constructor_dependencies": collect_service_constructor_dependency_violations,
    "service_module_thresholds": collect_service_module_threshold_violations,
    "transport_leakage": collect_transport_leakage_violations,
    "cross_domain_boundaries": collect_cross_domain_boundary_violations,
    "runtime_wrapper_service_surfaces": collect_runtime_wrapper_service_surface_violations,
}

_CUTOVER_WAVES = {
    "signals": "1",
    "predictions": "2",
    "cross_market": "2",
    "control_plane": "2",
    "market_structure": "2",
    "patterns": "2",
    "anomalies": "2",
    "market_data": "3",
    "news": "3",
    "indicators": "3",
    "portfolio": "3",
}


@dataclass(frozen=True)
class DomainScorecardRow:
    domain: str
    cutover_wave: str | None
    status: str
    service_files: int
    service_loc: int
    service_classes: int
    max_service_module_loc: int
    max_service_class_loc: int
    engine_files: int
    test_files: int
    total_violations: int
    violation_counts: dict[str, int]
    violation_symbols: dict[str, tuple[str, ...]]


def _iter_domains() -> tuple[str, ...]:
    return tuple(
        sorted(
            path.name
            for path in APPS_ROOT.iterdir()
            if path.is_dir() and not path.name.startswith("__")
        )
    )


def _service_stats(domain: str) -> tuple[int, int, int, int, int]:
    service_files = [path for path in iter_service_files() if path.relative_to(APPS_ROOT).parts[0] == domain]
    total_loc = 0
    total_service_classes = 0
    max_module_loc = 0
    max_class_size = 0
    for path in service_files:
        source = path.read_text(encoding="utf-8")
        tree = parse_module(path)
        module_loc = len(source.splitlines())
        total_loc += module_loc
        max_module_loc = max(max_module_loc, module_loc)
        service_classes = [
            node for node in tree.body if isinstance(node, ast.ClassDef) and node.name.endswith("Service")
        ]
        total_service_classes += len(service_classes)
        if service_classes:
            max_class_size = max(max_class_size, max(class_loc(node) for node in service_classes))
    return len(service_files), total_loc, total_service_classes, max_module_loc, max_class_size


def _engine_file_count(domain: str) -> int:
    return sum(1 for path in iter_engine_files() if path.relative_to(APPS_ROOT).parts[0] == domain)


def _test_file_count(domain: str) -> int:
    tests_root = BACKEND_ROOT / "tests" / "apps" / domain
    if not tests_root.exists():
        return 0
    return sum(1 for path in tests_root.glob("test_*.py") if path.is_file())


def _violations_by_domain() -> dict[str, dict[str, list[str]]]:
    grouped: dict[str, dict[str, list[str]]] = {}
    for category, collector in _VIOLATION_COLLECTORS.items():
        for violation in collector():
            parts = violation.path.split("/")
            if len(parts) < 3:
                continue
            domain = parts[2]
            domain_bucket = grouped.setdefault(domain, {})
            category_bucket = domain_bucket.setdefault(category, [])
            category_bucket.append(f"{violation.symbol} :: {violation.detail}")
    return grouped


def build_service_layer_scorecard() -> tuple[DomainScorecardRow, ...]:
    violations = _violations_by_domain()
    rows: list[DomainScorecardRow] = []
    for domain in _iter_domains():
        service_files, service_loc, service_classes, max_module_loc, max_class_loc = _service_stats(domain)
        violation_symbols = {
            category: tuple(sorted(items))
            for category, items in sorted(violations.get(domain, {}).items())
        }
        violation_counts = {category: len(items) for category, items in violation_symbols.items()}
        total_violations = sum(violation_counts.values())
        if total_violations == 0 and domain in _CUTOVER_WAVES:
            status = "clean"
        elif total_violations == 0:
            status = "stable"
        else:
            status = "debt-open"
        rows.append(
            DomainScorecardRow(
                domain=domain,
                cutover_wave=_CUTOVER_WAVES.get(domain),
                status=status,
                service_files=service_files,
                service_loc=service_loc,
                service_classes=service_classes,
                max_service_module_loc=max_module_loc,
                max_service_class_loc=max_class_loc,
                engine_files=_engine_file_count(domain),
                test_files=_test_file_count(domain),
                total_violations=total_violations,
                violation_counts=violation_counts,
                violation_symbols=violation_symbols,
            )
        )
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                999 if row.cutover_wave is None else int(row.cutover_wave),
                0 if row.status == "debt-open" else 1,
                row.domain,
            ),
        )
    )


def render_service_layer_scorecard(rows: tuple[DomainScorecardRow, ...]) -> str:
    clean_domains = sum(1 for row in rows if row.status == "clean")
    total_violations = sum(row.total_violations for row in rows)
    lines = [
        "# Service-Layer Architecture Scorecard",
        "",
        "Generated from repository facts collected by the architecture policy scanners.",
        "",
        f"- domains scanned: {len(rows)}",
        f"- clean cutover domains: {clean_domains}",
        f"- outstanding policy violations: {total_violations}",
        "",
        "| Domain | Service LOC / classes / files | Max hotspot | Engine files | Policy violations | Tests | Plan |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        violation_summary = "clean"
        if row.total_violations:
            parts = [f"{name}={count}" for name, count in sorted(row.violation_counts.items())]
            violation_summary = f"{row.total_violations} ({', '.join(parts)})"
        plan = f"Wave {row.cutover_wave}" if row.cutover_wave is not None else "unplanned"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row.domain}`",
                    f"`{row.service_loc} / {row.service_classes} / {row.service_files}`",
                    f"`module {row.max_service_module_loc} / class {row.max_service_class_loc}`",
                    f"`{row.engine_files}`",
                    violation_summary,
                    f"`{row.test_files}`",
                    f"{plan} / {row.status}",
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def scorecard_payload(rows: tuple[DomainScorecardRow, ...]) -> dict[str, object]:
    return {
        "summary": {
            "domains": len(rows),
            "clean_cutover_domains": sum(1 for row in rows if row.status == "clean"),
            "outstanding_policy_violations": sum(row.total_violations for row in rows),
        },
        "rows": [asdict(row) for row in rows],
    }


def write_service_layer_scorecard_markdown(*, rows: tuple[DomainScorecardRow, ...], output: str) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_service_layer_scorecard(rows), encoding="utf-8")
    return output_path


def write_service_layer_scorecard_json(*, rows: tuple[DomainScorecardRow, ...], output: str) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(scorecard_payload(rows), indent=2, sort_keys=True), encoding="utf-8")
    return output_path


__all__ = [
    "DomainScorecardRow",
    "build_service_layer_scorecard",
    "render_service_layer_scorecard",
    "scorecard_payload",
    "write_service_layer_scorecard_json",
    "write_service_layer_scorecard_markdown",
]
