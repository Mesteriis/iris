from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from src.core.errors.taxonomy import ErrorCategory, ErrorDomain, ErrorSeverity


class ErrorRegistryError(ValueError):
    """Base error for registry consistency failures."""


class DuplicateErrorCodeError(ErrorRegistryError):
    def __init__(self, error_code: str) -> None:
        super().__init__(f"Error code '{error_code}' is already registered.")
        self.error_code = error_code


class DuplicateMessageKeyError(ErrorRegistryError):
    def __init__(self, message_key: str) -> None:
        super().__init__(f"Message key '{message_key}' is already registered.")
        self.message_key = message_key


class UnknownErrorCodeError(ErrorRegistryError):
    def __init__(self, error_code: str) -> None:
        super().__init__(f"Error code '{error_code}' is not registered.")
        self.error_code = error_code


class UnknownMessageKeyError(ErrorRegistryError):
    def __init__(self, message_key: str) -> None:
        super().__init__(f"Message key '{message_key}' is not registered.")
        self.message_key = message_key


@dataclass(frozen=True, slots=True)
class ErrorDefinition:
    error_code: str
    message_key: str
    domain: ErrorDomain
    category: ErrorCategory
    http_status: int
    severity: ErrorSeverity
    retryable: bool = False
    safe_to_expose: bool = True


class ErrorRegistry:
    def __init__(self, definitions: Iterable[ErrorDefinition] = ()) -> None:
        self._definitions: dict[str, ErrorDefinition] = {}
        self._message_keys: dict[str, str] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: ErrorDefinition) -> ErrorDefinition:
        if definition.error_code in self._definitions:
            raise DuplicateErrorCodeError(definition.error_code)
        if definition.message_key in self._message_keys:
            raise DuplicateMessageKeyError(definition.message_key)
        self._definitions[definition.error_code] = definition
        self._message_keys[definition.message_key] = definition.error_code
        return definition

    def get(self, error_code: str) -> ErrorDefinition:
        definition = self._definitions.get(error_code)
        if definition is None:
            raise UnknownErrorCodeError(error_code)
        return definition

    def get_by_message_key(self, message_key: str) -> ErrorDefinition:
        error_code = self._message_keys.get(message_key)
        if error_code is None:
            raise UnknownMessageKeyError(message_key)
        return self.get(error_code)

    def __contains__(self, error_code: object) -> bool:
        return isinstance(error_code, str) and error_code in self._definitions

    def __iter__(self) -> Iterator[ErrorDefinition]:
        return iter(self._definitions.values())
