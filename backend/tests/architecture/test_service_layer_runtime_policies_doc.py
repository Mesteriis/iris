from __future__ import annotations

from pathlib import Path


def test_service_layer_runtime_policies_doc_exists() -> None:
    doc_path = Path(__file__).resolve().parents[3] / "docs" / "architecture" / "service-layer-runtime-policies.md"
    content = doc_path.read_text(encoding="utf-8")

    assert "## Domain Matrix" in content
    assert "`market_data`" in content
    assert "`portfolio`" in content
