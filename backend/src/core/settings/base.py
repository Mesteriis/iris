import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class AppLanguage(StrEnum):
    RU = "ru"
    EN = "en"
    ES = "es"
    UA = "ua"


class Settings(BaseSettings):
    app_name: str = "IRIS"
    app_version: str = Field(default="2026.03.15", alias="IRIS_VERSION")
    app_env: str = "development"
    language: AppLanguage = Field(default=AppLanguage.EN, alias="IRIS_LANGUAGE")
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_root_prefix: str = Field(default="/api", alias="IRIS_API_ROOT_PREFIX")
    api_version_prefix: str = Field(default="/v1", alias="IRIS_API_VERSION_PREFIX")
    api_launch_mode: str = Field(default="full", alias="IRIS_API_LAUNCH_MODE")
    api_deployment_profile: str = Field(default="platform_full", alias="IRIS_API_DEPLOYMENT_PROFILE")
    api_operation_ttl_seconds: int = Field(default=86400, alias="IRIS_API_OPERATION_TTL_SECONDS")
    ha_instance_id: str = Field(default="iris-main-001", alias="IRIS_HA_INSTANCE_ID")
    ha_display_name: str = Field(default="IRIS Main", alias="IRIS_HA_DISPLAY_NAME")
    ha_protocol_version: int = Field(default=1, alias="IRIS_HA_PROTOCOL_VERSION")
    ha_minimum_integration_version: str = Field(
        default="0.1.0",
        alias="IRIS_HA_MINIMUM_INTEGRATION_VERSION",
    )
    ha_recommended_integration_version: str = Field(
        default="0.1.0",
        alias="IRIS_HA_RECOMMENDED_INTEGRATION_VERSION",
    )
    ha_websocket_session_queue_depth: int = Field(
        default=1000,
        alias="IRIS_HA_WEBSOCKET_SESSION_QUEUE_DEPTH",
    )
    database_url: str = Field(
        default="postgresql+psycopg://iris:iris@db:5432/iris",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(
        default="redis://redis:6379/0",
        alias="REDIS_URL",
    )
    runtime_data_dir: str = Field(
        default_factory=lambda: str(Path(__file__).resolve().parents[3] / ".runtime"),
        alias="IRIS_RUNTIME_DATA_DIR",
    )
    event_stream_name: str = Field(default="iris_events", alias="EVENT_STREAM_NAME")
    polygon_api_key: str = Field(default="", alias="POLYGON_API_KEY")
    twelve_data_api_key: str = Field(default="", alias="TWELVE_DATA_API_KEY")
    alpha_vantage_api_key: str = Field(default="", alias="ALPHA_VANTAGE_API_KEY")
    fred_api_key: str = Field(default="", alias="FRED_API_KEY")
    eia_api_key: str = Field(default="", alias="EIA_API_KEY")
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        alias="CORS_ORIGINS",
    )
    taskiq_refresh_interval_seconds: int = 300
    taskiq_pattern_statistics_interval_seconds: int = 86400
    taskiq_market_structure_interval_seconds: int = 3600
    taskiq_market_structure_snapshot_poll_interval_seconds: int = 180
    taskiq_market_structure_health_interval_seconds: int = 60
    taskiq_market_structure_failure_backoff_base_seconds: int = 60
    taskiq_market_structure_failure_backoff_max_seconds: int = 1800
    taskiq_market_structure_quarantine_after_failures: int = 5
    taskiq_pattern_discovery_interval_seconds: int = 21600
    taskiq_strategy_discovery_interval_seconds: int = 21600
    taskiq_portfolio_sync_interval_seconds: int = 300
    taskiq_prediction_evaluation_interval_seconds: int = 600
    taskiq_hypothesis_eval_interval_seconds: int = 600
    taskiq_news_poll_interval_seconds: int = 180
    market_source_capability_refresh_on_startup: bool = Field(
        default=True,
        alias="IRIS_MARKET_SOURCE_CAPABILITY_REFRESH_ON_STARTUP",
    )
    market_source_capability_refresh_interval_seconds: int = Field(
        default=3600,
        alias="IRIS_MARKET_SOURCE_CAPABILITY_REFRESH_INTERVAL_SECONDS",
    )
    free_proxy_pool_enabled: bool = Field(default=True, alias="IRIS_FREE_PROXY_POOL_ENABLED")
    free_proxy_pool_source_urls: Annotated[list[str], NoDecode] = Field(
        default=[
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
            "https://raw.githubusercontent.com/fyvri/fresh-proxy-list/archive/storage/classic/http.json",
        ],
        alias="IRIS_FREE_PROXY_POOL_SOURCE_URLS",
    )
    free_proxy_pool_probe_urls: Annotated[list[str], NoDecode] = Field(
        default=[
            "https://finance.yahoo.com/robots.txt",
            "https://stooq.com/robots.txt",
        ],
        alias="IRIS_FREE_PROXY_POOL_PROBE_URLS",
    )
    free_proxy_pool_refresh_interval_seconds: int = Field(default=1800, alias="IRIS_FREE_PROXY_POOL_REFRESH_INTERVAL_SECONDS")
    free_proxy_pool_validation_batch_size: int = Field(default=32, alias="IRIS_FREE_PROXY_POOL_VALIDATION_BATCH_SIZE")
    free_proxy_pool_max_entries: int = Field(default=400, alias="IRIS_FREE_PROXY_POOL_MAX_ENTRIES")
    free_proxy_pool_request_timeout_seconds: float = Field(
        default=8.0,
        alias="IRIS_FREE_PROXY_POOL_REQUEST_TIMEOUT_SECONDS",
    )
    free_proxy_pool_persist_interval_seconds: int = Field(default=300, alias="IRIS_FREE_PROXY_POOL_PERSIST_INTERVAL_SECONDS")
    free_proxy_pool_max_proxy_attempts: int = Field(default=3, alias="IRIS_FREE_PROXY_POOL_MAX_PROXY_ATTEMPTS")
    free_proxy_pool_min_rating: float = Field(default=0.2, alias="IRIS_FREE_PROXY_POOL_MIN_RATING")
    taskiq_general_worker_processes: int = 1
    taskiq_analytics_worker_processes: int = 1
    event_worker_block_milliseconds: int = 1000
    event_worker_pending_idle_milliseconds: int = 30000
    event_worker_batch_size: int = 10
    control_plane_token: str = Field(default="", alias="IRIS_CONTROL_TOKEN")
    control_plane_dead_consumer_after_seconds: int = 300
    enable_hypothesis_engine: bool = False
    ai_openai_enabled: bool = Field(default=False, alias="IRIS_AI_OPENAI_ENABLED")
    ai_openai_base_url: str = "https://api.openai.com/v1"
    ai_openai_endpoint: str = "/chat/completions"
    ai_openai_api_key: str = ""
    ai_openai_model: str = "gpt-4.1-mini"
    ai_local_http_enabled: bool = Field(default=False, alias="IRIS_AI_LOCAL_HTTP_ENABLED")
    ai_local_http_base_url: str = "http://127.0.0.1:11434"
    ai_local_http_endpoint: str = "/api/generate"
    ai_local_http_model: str = "llama3.1:8b"
    ai_providers: Annotated[list[dict[str, Any]], NoDecode] = Field(default_factory=list, alias="IRIS_AI_PROVIDERS")
    ai_capabilities: Annotated[dict[str, Any], NoDecode] = Field(default_factory=dict, alias="IRIS_AI_CAPABILITIES")
    bootstrap_history_on_startup: bool = True
    portfolio_total_capital: float = 100_000.0
    portfolio_max_position_size: float = 0.05
    portfolio_max_positions: int = 20
    portfolio_max_sector_exposure: float = 0.25
    portfolio_stop_atr_multiplier: float = 2.0
    portfolio_take_profit_atr_multiplier: float = 3.0
    auto_watch_min_position_value: float = 100.0
    database_connect_retries: int = 30
    database_connect_retry_delay: float = 1.0
    redis_connect_retries: int = 30
    redis_connect_retry_delay: float = 1.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def normalize_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("free_proxy_pool_source_urls", "free_proxy_pool_probe_urls", mode="before")
    @classmethod
    def normalize_string_lists(cls, value: str | list[str] | None) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return [str(item).strip() for item in value if str(item).strip()]

    @field_validator("api_root_prefix", "api_version_prefix", mode="before")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized.rstrip("/") or "/"

    @field_validator("ai_providers", mode="before")
    @classmethod
    def normalize_ai_providers(cls, value: str | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if value in (None, ""):
            return []
        if isinstance(value, str):
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                raise TypeError("IRIS_AI_PROVIDERS must decode to a JSON array.")
            return [dict(item) for item in parsed if isinstance(item, dict)]
        return [dict(item) for item in value]

    @field_validator("ai_capabilities", mode="before")
    @classmethod
    def normalize_ai_capabilities(cls, value: str | dict[str, Any] | None) -> dict[str, Any]:
        if value in (None, ""):
            return {}
        if isinstance(value, str):
            parsed = json.loads(value)
            if not isinstance(parsed, dict):
                raise TypeError("IRIS_AI_CAPABILITIES must decode to a JSON object.")
            return dict(parsed)
        return dict(value)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
