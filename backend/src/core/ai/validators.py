from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from src.core.ai.contracts import AIValidationStatus


class AIPayloadValidationError(ValueError):
    def __init__(self, status: AIValidationStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


class PydanticOutputValidator[ModelT: BaseModel]:
    def __init__(
        self,
        *,
        contract_name: str,
        schema_contract: dict[str, Any] | str,
        model: type[ModelT],
        semantic_validator: Callable[[ModelT, str | None, str], None] | None = None,
    ) -> None:
        self.contract_name = contract_name
        self.schema_contract = schema_contract
        self._model = model
        self._semantic_validator = semantic_validator

    def validate(
        self,
        payload: dict[str, Any],
        *,
        requested_language: str | None,
        effective_language: str,
    ) -> dict[str, Any]:
        try:
            validated = self._model.model_validate(payload)
        except ValidationError as exc:
            raise AIPayloadValidationError(AIValidationStatus.INVALID_SCHEMA, str(exc)) from exc
        if self._semantic_validator is not None:
            try:
                self._semantic_validator(validated, requested_language, effective_language)
            except ValueError as exc:
                raise AIPayloadValidationError(AIValidationStatus.INVALID_SEMANTICS, str(exc)) from exc
        return validated.model_dump(mode="python")


__all__ = ["AIPayloadValidationError", "PydanticOutputValidator"]
