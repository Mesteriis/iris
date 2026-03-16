from datetime import UTC, datetime
from types import SimpleNamespace

from src.apps.briefs.api.presenters import brief_read
from src.apps.briefs.contracts import BriefKind


def test_brief_presenter_reads_generated_text_content_payload() -> None:
    now = datetime.now(UTC)
    item = SimpleNamespace(
        id=1,
        brief_kind=BriefKind.MARKET,
        scope_key="market",
        symbol=None,
        coin_id=None,
        content_kind="generated_text",
        content_json={
            "version": 1,
            "kind": "generated_text",
            "rendered_locale": "en",
            "title": "Market brief",
            "summary": "Leaders remain constructive while breadth stays selective.",
            "bullets": [
                "BTCUSD_EVT holds the strongest confidence profile.",
                "Broader breadth remains narrower than the headline momentum.",
            ],
        },
        refs_json={"scope": "market"},
        context_json={},
        provider="local_test",
        model="llama-test",
        prompt_name="brief.market",
        prompt_version=1,
        source_updated_at=now,
        created_at=now,
        updated_at=now,
    )

    payload = brief_read(item)

    assert payload.title == "Market brief"
    assert payload.summary == "Leaders remain constructive while breadth stays selective."
    assert payload.bullets == [
        "BTCUSD_EVT holds the strongest confidence profile.",
        "Broader breadth remains narrower than the headline momentum.",
    ]
    assert payload.content_kind == "generated_text"
    assert payload.rendered_locale == "en"
