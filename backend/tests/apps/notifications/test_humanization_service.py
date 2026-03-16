from iris.apps.notifications.services.humanization_service import render_template_notification


def test_render_template_notification_uses_shared_catalog_for_ru() -> None:
    payload = render_template_notification(
        {
            "event_type": "signal_created",
            "symbol": "BTCUSDT",
            "timeframe": 15,
            "payload": {"signal_type": "pattern_breakout"},
        },
        effective_language="ru",
    )

    assert payload["title"] == "BTCUSDT: новый сигнал"
    assert payload["message"] == (
        "IRIS зафиксировал сигнал pattern breakout по BTCUSDT на таймфрейме 15м. "
        "Проверь канонический сигнал перед действием."
    )
    assert payload["severity"] == "info"
    assert payload["urgency"] == "medium"


def test_render_template_notification_falls_back_to_en_for_unsupported_locale() -> None:
    payload = render_template_notification(
        {
            "event_type": "portfolio_balance_updated",
            "symbol": "ETHUSDT",
            "timeframe": 60,
            "payload": {
                "exchange_name": "binance",
                "balance": 1.25,
                "value_usd": 3210.5,
            },
        },
        effective_language="es",
    )

    assert payload["title"] == "ETHUSDT: balance updated"
    assert payload["message"] == (
        "Balance sync updated ETHUSDT on binance. Balance: 1.25, value: $3210.50."
    )
    assert payload["severity"] == "info"
    assert payload["urgency"] == "low"
