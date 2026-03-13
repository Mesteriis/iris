from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "IRIS"
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_root_prefix: str = Field(default="/api", alias="IRIS_API_ROOT_PREFIX")
    api_version_prefix: str = Field(default="/v1", alias="IRIS_API_VERSION_PREFIX")
    api_launch_mode: str = Field(default="full", alias="IRIS_API_LAUNCH_MODE")
    api_deployment_profile: str = Field(default="platform_full", alias="IRIS_API_DEPLOYMENT_PROFILE")
    api_operation_ttl_seconds: int = Field(default=86400, alias="IRIS_API_OPERATION_TTL_SECONDS")
    database_url: str = Field(
        default="postgresql+psycopg://iris:iris@db:5432/iris",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(
        default="redis://redis:6379/0",
        alias="REDIS_URL",
    )
    event_stream_name: str = Field(default="iris_events", alias="EVENT_STREAM_NAME")
    polygon_api_key: str = Field(default="", alias="POLYGON_API_KEY")
    twelve_data_api_key: str = Field(default="", alias="TWELVE_DATA_API_KEY")
    alpha_vantage_api_key: str = Field(default="", alias="ALPHA_VANTAGE_API_KEY")
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
    taskiq_general_worker_processes: int = 1
    taskiq_analytics_worker_processes: int = 1
    event_worker_block_milliseconds: int = 1000
    event_worker_pending_idle_milliseconds: int = 30000
    event_worker_batch_size: int = 10
    control_plane_token: str = Field(default="", alias="IRIS_CONTROL_TOKEN")
    control_plane_dead_consumer_after_seconds: int = 300
    enable_hypothesis_engine: bool = False
    ai_openai_base_url: str = "https://api.openai.com/v1"
    ai_openai_api_key: str = ""
    ai_openai_model: str = "gpt-4.1-mini"
    ai_local_http_base_url: str = "http://127.0.0.1:11434"
    ai_local_http_model: str = "llama3.1:8b"
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

    @field_validator("api_root_prefix", "api_version_prefix", mode="before")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized.rstrip("/") or "/"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
