import pytest
from iris.apps.news.exceptions import InvalidNewsSourceConfigurationError, UnsupportedNewsPluginError
from iris.apps.news.plugins import (
    DiscordBotNewsPlugin,
    TelegramUserNewsPlugin,
    TruthSocialUnsupportedPlugin,
    XNewsPlugin,
    list_registered_news_plugins,
)


def test_built_in_news_plugins_are_registered() -> None:
    plugins = list_registered_news_plugins()

    assert {"discord_bot", "telegram_user", "truth_social", "x"} <= set(plugins)
    assert plugins["truth_social"].descriptor.supported is False
    assert plugins["telegram_user"].descriptor.supports_user_identity is True


def test_x_plugin_requires_token() -> None:
    with pytest.raises(InvalidNewsSourceConfigurationError, match=r"bearer_token or credentials\.access_token"):
        XNewsPlugin.validate_configuration(
            credentials={},
            settings={"user_id": "12345"},
        )


def test_discord_and_telegram_plugins_validate_required_fields() -> None:
    DiscordBotNewsPlugin.validate_configuration(
        credentials={"bot_token": "discord-token"},
        settings={"channel_id": "987654321"},
    )
    TelegramUserNewsPlugin.validate_configuration(
        credentials={
            "api_id": "1000",
            "api_hash": "hash",
            "session_string": "session",
        },
        settings={"channel": "@irisnews"},
    )
    TelegramUserNewsPlugin.validate_configuration(
        credentials={
            "api_id": "1000",
            "api_hash": "hash",
            "session_string": "session",
        },
        settings={
            "entity_type": "channel",
            "entity_id": 101,
            "entity_access_hash": "202",
        },
    )


def test_telegram_plugin_rejects_incomplete_private_channel_settings() -> None:
    with pytest.raises(InvalidNewsSourceConfigurationError, match="entity_access_hash"):
        TelegramUserNewsPlugin.validate_configuration(
            credentials={
                "api_id": "1000",
                "api_hash": "hash",
                "session_string": "session",
            },
            settings={
                "entity_type": "channel",
                "entity_id": 101,
            },
        )


def test_truth_social_plugin_is_explicitly_unsupported() -> None:
    with pytest.raises(UnsupportedNewsPluginError, match="developer API"):
        TruthSocialUnsupportedPlugin.validate_configuration(
            credentials={},
            settings={},
        )
