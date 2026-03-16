import os
from urllib.parse import urlsplit

import pytest
from iris.core.settings import Settings
from redis import Redis
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def _testcontainers_enabled() -> bool:
    raw = os.getenv("IRIS_TEST_USE_TESTCONTAINERS")
    if raw is None:
        return True
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@pytest.mark.skipif(not _testcontainers_enabled(), reason="testcontainers bootstrap disabled")
def test_backend_tests_use_isolated_postgres_and_redis(
    db_session: Session,
    redis_client: Redis,
    settings: Settings,
) -> None:
    database_url = make_url(settings.database_url)
    redis_url = urlsplit(settings.redis_url)

    assert database_url.host != "db"
    assert database_url.database == os.getenv("IRIS_TEST_POSTGRES_DB", "iris_test")
    assert settings.database_url != "postgresql+psycopg://iris:iris@db:5432/iris"

    assert redis_url.hostname != "redis"
    assert settings.redis_url != "redis://redis:6379/0"
    assert settings.event_stream_name == "iris_events_test"

    assert db_session.execute(text("SELECT current_database()")).scalar_one() == database_url.database
    assert redis_client.ping() is True
