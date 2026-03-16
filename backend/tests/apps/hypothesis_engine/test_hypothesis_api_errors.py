from src.apps.hypothesis_engine.api.errors import hypothesis_error_to_http
from src.apps.hypothesis_engine.exceptions import PromptVeilLockedError


def test_hypothesis_api_errors_are_localized_from_registry() -> None:
    error = hypothesis_error_to_http(PromptVeilLockedError(), locale="ru")

    assert error is not None
    assert error.status_code == 423
    assert error.detail["message_key"] == "error.hypothesis.prompt_veil_locked"
    assert error.detail["message"] == "Запрошенное семейство prompt скрыто veil и пока недоступно для редактирования."
