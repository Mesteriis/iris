from __future__ import annotations

from tests.architecture.service_layer_policy import ArchitectureViolation

EXPECTED_ENGINE_PURITY_VIOLATIONS: tuple[ArchitectureViolation, ...] = ()

EXPECTED_SERVICE_RESULT_CONTRACT_VIOLATIONS: tuple[ArchitectureViolation, ...] = (
    ArchitectureViolation(
        path="src/apps/hypothesis_engine/services/weight_update_service.py",
        symbol="WeightUpdateService.apply_to_evaluation",
        detail="tuple[str, dict[str, object]] | None",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_bootstrap.py",
        symbol="PatternBootstrapService.bootstrap_scan",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/portfolio/services.py",
        symbol="PortfolioActionEvaluationResult.to_payload",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/portfolio/services.py",
        symbol="PortfolioCachedBalanceRow.to_payload",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/portfolio/services.py",
        symbol="PortfolioSyncItem.to_payload",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/portfolio/services.py",
        symbol="PortfolioSyncResult.to_payload",
        detail="dict[str, object]",
    ),
)

EXPECTED_SERVICE_CONSTRUCTOR_DEPENDENCY_VIOLATIONS: tuple[ArchitectureViolation, ...] = ()

EXPECTED_TRANSPORT_LEAKAGE_VIOLATIONS: tuple[ArchitectureViolation, ...] = (
    ArchitectureViolation(
        path="src/apps/hypothesis_engine/services/prompt_service.py",
        symbol="src.apps.hypothesis_engine.schemas",
        detail="import",
    ),
)

EXPECTED_CROSS_DOMAIN_BOUNDARY_VIOLATIONS: tuple[ArchitectureViolation, ...] = (
    ArchitectureViolation(
        path="src/apps/patterns/task_service_base.py",
        symbol="src.apps.cross_market.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_base.py",
        symbol="src.apps.indicators.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_base.py",
        symbol="src.apps.market_data.repositories",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_base.py",
        symbol="src.apps.signals.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_bootstrap.py",
        symbol="src.apps.market_data.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_bootstrap.py",
        symbol="src.apps.signals.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_context.py",
        symbol="src.apps.cross_market.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_context.py",
        symbol="src.apps.indicators.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_context.py",
        symbol="src.apps.market_data.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_context.py",
        symbol="src.apps.signals.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_decisions.py",
        symbol="src.apps.cross_market.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_decisions.py",
        symbol="src.apps.indicators.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_decisions.py",
        symbol="src.apps.market_data.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_decisions.py",
        symbol="src.apps.signals.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_history.py",
        symbol="src.apps.signals.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_market.py",
        symbol="src.apps.cross_market.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_market.py",
        symbol="src.apps.indicators.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_market.py",
        symbol="src.apps.market_data.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_market.py",
        symbol="src.apps.signals.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/portfolio/services.py",
        symbol="src.apps.market_data.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/portfolio/services.py",
        symbol="src.apps.market_data.repositories",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/portfolio/services.py",
        symbol="src.apps.signals.models",
        detail="import",
    ),
)

EXPECTED_SERVICE_MODULE_THRESHOLD_VIOLATIONS: tuple[ArchitectureViolation, ...] = (
    ArchitectureViolation(
        path="src/apps/patterns/task_service_base.py",
        symbol="__module__",
        detail="module_loc=349",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_decisions.py",
        symbol="__module__",
        detail="module_loc=489",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_market.py",
        symbol="__module__",
        detail="module_loc=454",
    ),
    ArchitectureViolation(
        path="src/apps/portfolio/services.py",
        symbol="PortfolioService",
        detail="class_loc=522",
    ),
    ArchitectureViolation(
        path="src/apps/portfolio/services.py",
        symbol="__module__",
        detail="module_loc=699",
    ),
)
