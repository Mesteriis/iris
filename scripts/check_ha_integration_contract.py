#!/usr/bin/env python3
from __future__ import annotations

import argparse
import configparser
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPATIBILITY_PATH = ROOT / "ha" / "compatibility.yaml"
GITMODULES_PATH = ROOT / ".gitmodules"
INTEGRATION_PATH = ROOT / "ha" / "integration"
MANIFEST_PATH = INTEGRATION_PATH / "custom_components" / "iris" / "manifest.json"
PYPROJECT_PATH = INTEGRATION_PATH / "pyproject.toml"
SETTINGS_PATH = ROOT / "backend" / "iris" / "core" / "settings" / "base.py"
FIXTURES_ROOT = INTEGRATION_PATH / "tests" / "fixtures" / "contract"
HA_CONTRACT_SOURCE_PREFIXES = (
    "backend/iris/apps/integrations/ha/",
)
HA_CONTRACT_SOURCE_FILES = {
    "backend/iris/core/settings/base.py",
}
HA_CONTRACT_COMPANION_PREFIXES = (
    "ha/integration/",
    "ha/integration/tests/fixtures/contract/",
)
HA_CONTRACT_COMPANION_FILES = {
    "docs/home-assistant/protocol-specification.md",
    "ha/compatibility.yaml",
    "ha/integration",
}


class ContractCheckError(RuntimeError):
    pass


def main() -> int:
    args = _parse_args()
    compatibility = _parse_simple_yaml(COMPATIBILITY_PATH)
    _check_compatibility_shape(compatibility)
    _check_gitmodules(compatibility)
    _check_submodule_gitlink(compatibility)
    _check_integration_files(compatibility)
    _check_backend_settings(compatibility)
    changed_paths = _resolve_changed_paths(args)
    if changed_paths is not None:
        _check_diff_guard(changed_paths)
    print("HA integration contract checks passed.")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate HA integration contract and drift guard.")
    parser.add_argument("--base-ref", help="Git base ref/sha for diff-aware drift guard.")
    parser.add_argument("--head-ref", help="Git head ref/sha for diff-aware drift guard.")
    parser.add_argument(
        "--changed-path",
        action="append",
        default=[],
        help="Explicit changed path for drift-guard testing. Can be repeated.",
    )
    return parser.parse_args()


def _parse_simple_yaml(path: Path) -> dict[str, object]:
    result: dict[str, object] = {}
    current_section: dict[str, str] | None = None
    current_name: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if indent == 0:
            if value:
                result[key] = _coerce_scalar(value)
                current_section = None
                current_name = None
            else:
                section: dict[str, str] = {}
                result[key] = section
                current_section = section
                current_name = key
            continue
        if indent != 2 or current_section is None or current_name is None:
            raise ContractCheckError(f"Unsupported compatibility format at line: {raw_line}")
        current_section[key] = _strip_quotes(value)
    return result


def _coerce_scalar(value: str) -> object:
    value = _strip_quotes(value)
    if value.isdigit():
        return int(value)
    return value


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _check_compatibility_shape(compatibility: dict[str, object]) -> None:
    required_top = {"protocol_version", "backend", "integration"}
    missing = required_top - compatibility.keys()
    if missing:
        raise ContractCheckError(f"Missing keys in ha/compatibility.yaml: {sorted(missing)}")
    if not isinstance(compatibility["protocol_version"], int):
        raise ContractCheckError("ha/compatibility.yaml protocol_version must be an integer.")
    for section_name in ("backend", "integration"):
        section = compatibility[section_name]
        if not isinstance(section, dict):
            raise ContractCheckError(f"ha/compatibility.yaml section '{section_name}' must be a mapping.")


def _check_gitmodules(compatibility: dict[str, object]) -> None:
    parser = configparser.ConfigParser()
    parser.read(GITMODULES_PATH, encoding="utf-8")
    section_name = 'submodule "ha/integration"'
    if section_name not in parser:
        raise ContractCheckError("Missing ha/integration submodule entry in .gitmodules.")
    section = parser[section_name]
    compatibility_integration = compatibility["integration"]
    assert isinstance(compatibility_integration, dict)
    expected_path = compatibility_integration["path"]
    expected_url = compatibility_integration["repository"]
    if section.get("path") != expected_path:
        raise ContractCheckError(
            f".gitmodules path mismatch for ha/integration: expected {expected_path!r}, got {section.get('path')!r}."
        )
    if section.get("url") != expected_url:
        raise ContractCheckError(
            f".gitmodules url mismatch for ha/integration: expected {expected_url!r}, got {section.get('url')!r}."
        )


def _check_submodule_gitlink(compatibility: dict[str, object]) -> None:
    compatibility_integration = compatibility["integration"]
    assert isinstance(compatibility_integration, dict)
    expected_path = str(compatibility_integration["path"])
    result = subprocess.run(
        ["git", "ls-files", "--stage", expected_path],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    output = result.stdout.strip()
    if not output:
        raise ContractCheckError(f"Submodule path {expected_path!r} is not tracked in git.")
    if not output.startswith("160000 "):
        raise ContractCheckError(f"Path {expected_path!r} is not a gitlink/submodule entry.")
    parts = output.split()
    if len(parts) < 2:
        raise ContractCheckError(f"Unable to parse gitlink metadata for {expected_path!r}.")
    gitlink_sha = parts[1]
    expected_sha = compatibility_integration.get("pinned_commit")
    if not isinstance(expected_sha, str) or not expected_sha:
        raise ContractCheckError("ha/compatibility.yaml integration.pinned_commit must be a non-empty string.")
    if gitlink_sha != expected_sha:
        raise ContractCheckError(
            "Submodule gitlink SHA does not match ha/compatibility.yaml integration.pinned_commit. "
            f"git={gitlink_sha}, compatibility={expected_sha}."
        )


def _check_integration_files(compatibility: dict[str, object]) -> None:
    required_files = [
        INTEGRATION_PATH / "README.md",
        INTEGRATION_PATH / "hacs.json",
        INTEGRATION_PATH / ".github" / "workflows" / "ci.yml",
        MANIFEST_PATH,
        PYPROJECT_PATH,
        FIXTURES_ROOT / "bootstrap.json",
        FIXTURES_ROOT / "catalog.json",
        FIXTURES_ROOT / "dashboard.json",
        FIXTURES_ROOT / "state.json",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required_files if not path.exists()]
    if missing:
        raise ContractCheckError(f"Missing required integration repo files: {missing}")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    project_version = pyproject["project"]["version"]
    manifest_version = manifest["version"]

    compatibility_integration = compatibility["integration"]
    assert isinstance(compatibility_integration, dict)
    minimum_version = compatibility_integration["minimum_version"]
    recommended_version = compatibility_integration["recommended_version"]

    if project_version != manifest_version:
        raise ContractCheckError(
            f"Integration version mismatch: pyproject={project_version}, manifest={manifest_version}."
        )
    if recommended_version != project_version or minimum_version != project_version:
        raise ContractCheckError(
            "ha/compatibility.yaml integration versions must match the current integration release version."
        )


def _check_backend_settings(compatibility: dict[str, object]) -> None:
    text = SETTINGS_PATH.read_text(encoding="utf-8")
    backend_version = _extract_setting(text, "app_version")
    protocol_version = int(_extract_setting(text, "ha_protocol_version"))
    minimum_integration_version = _extract_setting(text, "ha_minimum_integration_version")
    recommended_integration_version = _extract_setting(text, "ha_recommended_integration_version")

    compatibility_backend = compatibility["backend"]
    compatibility_integration = compatibility["integration"]
    assert isinstance(compatibility_backend, dict)
    assert isinstance(compatibility_integration, dict)

    if compatibility["protocol_version"] != protocol_version:
        raise ContractCheckError(
            f"Protocol version mismatch: settings={protocol_version}, ha/compatibility.yaml={compatibility['protocol_version']}."
        )
    if compatibility_backend["minimum_version"] != backend_version:
        raise ContractCheckError(
            f"Backend minimum version mismatch: settings={backend_version}, compatibility={compatibility_backend['minimum_version']}."
        )
    if compatibility_backend["recommended_version"] != backend_version:
        raise ContractCheckError(
            f"Backend recommended version mismatch: settings={backend_version}, compatibility={compatibility_backend['recommended_version']}."
        )
    if compatibility_integration["minimum_version"] != minimum_integration_version:
        raise ContractCheckError(
            "Integration minimum version mismatch between backend settings and ha/compatibility.yaml."
        )
    if compatibility_integration["recommended_version"] != recommended_integration_version:
        raise ContractCheckError(
            "Integration recommended version mismatch between backend settings and ha/compatibility.yaml."
        )


def _resolve_changed_paths(args: argparse.Namespace) -> set[str] | None:
    if args.changed_path:
        return set(args.changed_path)
    if bool(args.base_ref) != bool(args.head_ref):
        raise ContractCheckError("Both --base-ref and --head-ref must be provided together.")
    if args.base_ref and args.head_ref:
        return _git_changed_paths(str(args.base_ref), str(args.head_ref))
    return None


def _git_changed_paths(base_ref: str, head_ref: str) -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}..{head_ref}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _check_diff_guard(changed_paths: set[str]) -> None:
    if not changed_paths:
        return
    source_paths = sorted(path for path in changed_paths if _is_contract_source_path(path))
    if not source_paths:
        return
    companion_paths = sorted(path for path in changed_paths if _is_contract_companion_path(path))
    if companion_paths:
        return
    raise ContractCheckError(
        "HA backend contract files changed without companion updates. "
        f"Changed contract paths: {source_paths}. "
        "Expected at least one of: docs/home-assistant/protocol-specification.md, ha/compatibility.yaml, ha/integration (submodule ref or files)."
    )


def _is_contract_source_path(path: str) -> bool:
    return path in HA_CONTRACT_SOURCE_FILES or any(path.startswith(prefix) for prefix in HA_CONTRACT_SOURCE_PREFIXES)


def _is_contract_companion_path(path: str) -> bool:
    return path in HA_CONTRACT_COMPANION_FILES or any(
        path.startswith(prefix) for prefix in HA_CONTRACT_COMPANION_PREFIXES
    )


def _extract_setting(text: str, field_name: str) -> str:
    pattern = rf"{field_name}:.*?Field\(\s*default=(?P<quote>[\"']?)(?P<value>.*?)(?P=quote),"
    match = re.search(pattern, text, re.S)
    if match is None:
        raise ContractCheckError(f"Unable to locate setting {field_name!r} in backend settings.")
    return match.group("value")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractCheckError as exc:
        print(f"HA integration contract check failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
