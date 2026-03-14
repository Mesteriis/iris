from __future__ import annotations

from pathlib import Path


def test_service_layer_adr_package_exists() -> None:
    adr_root = Path(__file__).resolve().parents[3] / "docs" / "architecture" / "adr"
    expected = {
        "0010-caller-owns-commit-boundary.md",
        "0011-analytical-engines-never-fetch.md",
        "0012-services-return-domain-contracts.md",
        "0013-async-classes-for-orchestration-pure-functions-for-analysis.md",
        "0014-post-commit-side-effects-only.md",
    }

    assert expected.issubset({path.name for path in adr_root.iterdir() if path.is_file()})
