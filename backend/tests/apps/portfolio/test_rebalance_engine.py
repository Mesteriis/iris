from iris.apps.portfolio.engines.rebalance_engine import build_rebalance_plan


def test_rebalance_engine_closes_position_when_target_is_zero() -> None:
    plan = build_rebalance_plan(
        current_value=250.0,
        target_value=0.0,
        entry_price=50.0,
        atr_14=2.5,
    )

    assert plan.action == "CLOSE_POSITION"
    assert plan.action_size == 250.0
    assert plan.position_value == 0.0
    assert plan.position_size == 0.0
    assert plan.status == "closed"


def test_rebalance_engine_opens_new_position_from_empty_state() -> None:
    plan = build_rebalance_plan(
        current_value=0.0,
        target_value=300.0,
        entry_price=60.0,
        atr_14=3.0,
    )

    assert plan.action == "OPEN_POSITION"
    assert plan.action_size == 300.0
    assert plan.position_value == 300.0
    assert plan.position_size == 5.0
    assert plan.status == "open"
    assert plan.stop_loss is not None
    assert plan.take_profit is not None


def test_rebalance_engine_reduces_existing_position_on_large_negative_delta() -> None:
    plan = build_rebalance_plan(
        current_value=400.0,
        target_value=150.0,
        entry_price=50.0,
        atr_14=2.0,
    )

    assert plan.action == "REDUCE_POSITION"
    assert plan.action_size == 250.0
    assert plan.position_value == 150.0
    assert plan.position_size == 3.0
    assert plan.status == "partial"
