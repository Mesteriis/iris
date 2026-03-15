from __future__ import annotations

from src.apps.integrations.ha.application.services import HABridgeService
from src.core.settings import AppLanguage, Settings


def test_ha_catalog_and_dashboard_use_shared_ru_catalog_labels() -> None:
    settings = Settings()
    settings.language = AppLanguage.RU
    service = HABridgeService(settings=settings)

    catalog = service.catalog().model_dump(mode="json")
    dashboard = service.dashboard().model_dump(mode="json")

    entity_names = {item["entity_key"]: item["name"] for item in catalog["entities"]}
    command_names = {item["command_key"]: item["name"] for item in catalog["commands"]}
    view_titles = {item["view_key"]: item["title"] for item in dashboard["views"]}

    assert entity_names["system.connection"] == "Подключение IRIS"
    assert entity_names["settings.default_timeframe"] == "Таймфрейм по умолчанию"
    assert command_names["portfolio.sync"] == "Синхронизация портфеля"
    assert view_titles["overview"] == "Обзор"
    assert dashboard["views"][0]["sections"][0]["widgets"][0]["title"] == "Подключение"
