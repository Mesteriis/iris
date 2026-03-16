from tests.architecture.service_layer_scorecard import (
    build_service_layer_scorecard,
    render_service_layer_scorecard,
    scorecard_payload,
)


def test_service_layer_scorecard_builds_current_domain_snapshot() -> None:
    rows = build_service_layer_scorecard()
    by_domain = {row.domain: row for row in rows}

    assert "signals" in by_domain
    assert "portfolio" in by_domain
    assert by_domain["portfolio"].cutover_wave == "3"
    assert by_domain["portfolio"].total_violations == 0
    assert by_domain["signals"].engine_files >= 1


def test_service_layer_scorecard_renders_markdown_and_json() -> None:
    rows = build_service_layer_scorecard()
    markdown = render_service_layer_scorecard(rows)
    payload = scorecard_payload(rows)

    assert "# Service-Layer Architecture Scorecard" in markdown
    assert "| Domain | Service LOC / classes / files |" in markdown
    assert any(item["domain"] == "portfolio" for item in payload["rows"])
    assert payload["summary"]["domains"] == len(rows)
