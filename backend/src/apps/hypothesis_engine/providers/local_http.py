from src.core.ai.contracts import AICapability, AIProviderConfig, AIProviderKind
from src.core.ai.providers.local_http import LocalHTTPProvider as CoreLocalHTTPProvider


class LocalHTTPProvider(CoreLocalHTTPProvider):
    provider_name = "local_http"

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        endpoint: str = "/api/generate",
        timeout: float = 15.0,
    ) -> None:
        super().__init__(
            AIProviderConfig(
                name=self.provider_name,
                kind=AIProviderKind.LOCAL_HTTP,
                enabled=True,
                base_url=base_url,
                endpoint=endpoint,
                auth_token=None,
                auth_header="Authorization",
                auth_scheme=None,
                model=model,
                timeout_seconds=timeout,
                priority=1,
                capabilities=(AICapability.HYPOTHESIS_GENERATE,),
            )
        )
