from iris.apps.news.contracts import (
    TelegramWizardFieldRead,
    TelegramWizardRead,
    TelegramWizardStepRead,
)
from iris.core.http.router_policy import api_path


def telegram_wizard_spec() -> TelegramWizardRead:
    return TelegramWizardRead(
        plugin_name="telegram_user",
        title="Telegram News Source Wizard",
        supported_dialog_types=["channel", "chat"],
        private_dialog_support=True,
        steps=[
            TelegramWizardStepRead(
                id="request_code",
                title="Request Login Code",
                description="Send Telegram login code to the user's phone number.",
                endpoint=api_path("/news/onboarding/telegram/session/request"),
                method="POST",
                fields=[
                    TelegramWizardFieldRead(id="api_id", label="API ID", type="number", required=True),
                    TelegramWizardFieldRead(id="api_hash", label="API Hash", type="text", required=True, secret=True),
                    TelegramWizardFieldRead(id="phone_number", label="Phone Number", type="tel", required=True),
                ],
            ),
            TelegramWizardStepRead(
                id="confirm_code",
                title="Confirm Session",
                description="Exchange the received code for a reusable MTProto session string.",
                endpoint=api_path("/news/onboarding/telegram/session/confirm"),
                method="POST",
                fields=[
                    TelegramWizardFieldRead(id="code", label="Login Code", type="text", required=True),
                    TelegramWizardFieldRead(
                        id="password",
                        label="2FA Password",
                        type="password",
                        required=False,
                        secret=True,
                    ),
                ],
            ),
            TelegramWizardStepRead(
                id="list_dialogs",
                title="Choose Dialogs",
                description="Load channels and groups available to the authenticated Telegram account.",
                endpoint=api_path("/news/onboarding/telegram/dialogs"),
                method="POST",
                fields=[
                    TelegramWizardFieldRead(
                        id="session_string",
                        label="Session String",
                        type="text",
                        required=True,
                        secret=True,
                    ),
                    TelegramWizardFieldRead(
                        id="include_users",
                        label="Include User Chats",
                        type="boolean",
                        required=False,
                    ),
                ],
            ),
            TelegramWizardStepRead(
                id="create_sources",
                title="Create News Sources",
                description="Create one or more IRIS news sources from the selected Telegram dialogs.",
                endpoint=api_path("/news/onboarding/telegram/sources/bulk"),
                method="POST",
                fields=[
                    TelegramWizardFieldRead(id="dialogs", label="Selected Dialogs", type="array", required=True),
                ],
            ),
        ],
        notes=[
            "Public channels can be stored via @username.",
            "Private channels require entity_id plus entity_access_hash.",
            "Private legacy groups can be stored via entity_type=chat and entity_id.",
            "Only explicitly selected dialogs are polled; IRIS does not ingest all dialogs automatically.",
        ],
        source_payload_example={
            "plugin_name": "telegram_user",
            "display_name": "Alpha Channel",
            "credentials": {
                "api_id": 1001,
                "api_hash": "telegram-api-hash",
                "session_string": "telegram-session-string",
            },
            "settings": {
                "entity_type": "channel",
                "entity_id": 101,
                "entity_access_hash": "999",
                "channel": "@alpha",
            },
        },
    )


__all__ = ["telegram_wizard_spec"]
