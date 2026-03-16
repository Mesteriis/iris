from pathlib import Path


def test_service_layer_performance_budgets_doc_exists() -> None:
    doc_path = Path(__file__).resolve().parents[3] / "docs" / "architecture" / "service-layer-performance-budgets.md"
    content = doc_path.read_text(encoding="utf-8")

    assert "## Budget Matrix" in content
    assert "`market_data` coin history sync" in content
    assert "`patterns` discovery / strategy discovery" in content
