# ruff: noqa: RUF001

TRANSLATIONS: dict[str, str] = {
    "errors.control_plane.control_mode_required": "Для изменений topology требуется режим control.",
    "errors.control_plane.control_token_invalid": "Control token отсутствует или недействителен.",
    "errors.control_plane.detail.allowed_access_modes": "Допустимые режимы доступа.",
    "errors.control_plane.detail.current_version": "Актуальная опубликованная версия topology.",
    "errors.control_plane.detail.draft_id": "Идентификатор draft.",
    "errors.control_plane.detail.expected_version": "Базовая версия topology для draft.",
    "errors.control_plane.invalid_access_mode": "Заголовок X-IRIS-Access-Mode должен содержать один из поддерживаемых режимов доступа.",
    "errors.generic.internal": "Операция завершилась внутренней ошибкой сервиса.",
    "errors.generic.authentication_failed": "Аутентификация для запрошенной операции не пройдена.",
    "errors.generic.authorization_denied": "Запрос не авторизован для текущей control surface.",
    "errors.generic.concurrency_conflict": "Ресурс изменился конкурентно. Повторите операцию на актуальной версии.",
    "errors.generic.duplicate_request": "Запрос конфликтует с уже существующим ресурсом.",
    "errors.generic.integration_unreachable": "Требуемая внешняя интеграция сейчас недоступна.",
    "errors.generic.invalid_state_transition": "Запрошенная операция недопустима в текущем состоянии.",
    "errors.generic.policy_denied": "Запрос отклонен политикой.",
    "errors.generic.resource_not_found": "Запрошенный ресурс '{resource}' не найден.",
    "errors.generic.validation_failed": "Тело запроса не прошло валидацию.",
    "errors.ha.command_not_available": "Команда '{command}' недоступна на текущей стадии HA bridge.",
    "errors.ha.invalid_payload": "Команда '{command}' получила некорректный payload.",
    "errors.hypothesis.prompt_veil_locked": "Запрошенное семейство prompt скрыто veil и пока недоступно для редактирования.",
}
