from __future__ import annotations

from src.core.ai.contracts import AICapability, AIProviderConfig, AIProviderKind
from src.core.ai.providers.openai_like import OpenAILikeProvider as CoreOpenAILikeProvider


class OpenAILikeProvider(CoreOpenAILikeProvider):
    provider_name = "openai_like"

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        timeout: float = 15.0,
    ) -> None:
        super().__init__(
            AIProviderConfig(
                name=self.provider_name,
                kind=AIProviderKind.OPENAI_LIKE,
                enabled=True,
                base_url=base_url,
                endpoint="/chat/completions",
                auth_token=api_key,
                auth_header="Authorization",
                auth_scheme="Bearer",
                model=model,
                timeout_seconds=timeout,
                priority=1,
                capabilities=(AICapability.HYPOTHESIS_GENERATE,),
            )
        )
