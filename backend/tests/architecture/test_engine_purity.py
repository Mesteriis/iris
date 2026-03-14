from __future__ import annotations

from tests.architecture.service_layer_baseline import EXPECTED_ENGINE_PURITY_VIOLATIONS
from tests.architecture.service_layer_policy import (
    assert_policy_matches_baseline,
    collect_engine_purity_violations,
)


def test_engine_purity_policy() -> None:
    assert_policy_matches_baseline(
        actual=collect_engine_purity_violations(),
        expected=EXPECTED_ENGINE_PURITY_VIOLATIONS,
    )

