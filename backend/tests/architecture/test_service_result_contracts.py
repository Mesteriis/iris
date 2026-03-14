from __future__ import annotations

from tests.architecture.service_layer_baseline import EXPECTED_SERVICE_RESULT_CONTRACT_VIOLATIONS
from tests.architecture.service_layer_policy import (
    assert_policy_matches_baseline,
    collect_service_result_contract_violations,
)


def test_service_result_contract_policy() -> None:
    assert_policy_matches_baseline(
        actual=collect_service_result_contract_violations(),
        expected=EXPECTED_SERVICE_RESULT_CONTRACT_VIOLATIONS,
    )
