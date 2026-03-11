from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "IRIS"
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = Field(
        default="postgresql+psycopg://iris:iris@db:5432/iris",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(
        default="redis://redis:6379/0",
        alias="REDIS_URL",
    )
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
    taskiq_metrics_refresh_interval_seconds: int = 300
    taskiq_analytics_event_interval_seconds: int = 900
    taskiq_pattern_statistics_interval_seconds: int = 86400
    taskiq_market_structure_interval_seconds: int = 3600
    taskiq_pattern_discovery_interval_seconds: int = 21600
    taskiq_strategy_discovery_interval_seconds: int = 21600
    bootstrap_history_on_startup: bool = True
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
