from tests.architecture.service_layer_baseline import EXPECTED_TRANSPORT_LEAKAGE_VIOLATIONS
from tests.architecture.service_layer_policy import (
    assert_policy_matches_baseline,
    collect_transport_leakage_violations,
)


def test_transport_leakage_policy() -> None:
    assert_policy_matches_baseline(
        actual=collect_transport_leakage_violations(),
        expected=EXPECTED_TRANSPORT_LEAKAGE_VIOLATIONS,
    )
