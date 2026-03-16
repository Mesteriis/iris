from iris.apps.notifications.api.errors import notification_not_found_error


def test_notification_api_error_uses_settings_compatible_localized_shape() -> None:
    error = notification_not_found_error(locale="en")

    assert error.status_code == 404
    assert error.detail["code"] == "resource_not_found"
    assert error.detail["message_key"] == "error.resource.not_found"
    assert error.detail["message"] == "The requested notification was not found."
    assert error.detail["safe_to_expose"] is True
