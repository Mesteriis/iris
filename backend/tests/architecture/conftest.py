from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    return None


@pytest.fixture(autouse=True)
def isolated_event_stream() -> Iterator[None]:
    yield


@pytest.fixture(autouse=True)
def cleanup_test_coins() -> Iterator[None]:
    yield


@pytest.fixture(autouse=True)
def cleanup_portfolio_state() -> Iterator[None]:
    yield


@pytest.fixture(autouse=True)
def cleanup_pattern_state() -> Iterator[None]:
    yield


@pytest.fixture(autouse=True)
def cleanup_anomaly_state() -> Iterator[None]:
    yield


@pytest.fixture(autouse=True)
def cleanup_market_structure_state() -> Iterator[None]:
    yield


@pytest.fixture(autouse=True)
def cleanup_news_state() -> Iterator[None]:
    yield


@pytest.fixture(autouse=True)
def cleanup_hypothesis_state() -> Iterator[None]:
    yield


@pytest.fixture(autouse=True)
def ensure_control_plane_audit_seed() -> Iterator[None]:
    yield
