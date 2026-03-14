from __future__ import annotations

from tests.architecture.service_layer_policy import ArchitectureViolation

EXPECTED_ENGINE_PURITY_VIOLATIONS: tuple[ArchitectureViolation, ...] = ()

EXPECTED_SERVICE_RESULT_CONTRACT_VIOLATIONS: tuple[ArchitectureViolation, ...] = (
    ArchitectureViolation(
        path="src/apps/anomalies/services/anomaly_service.py",
        symbol="AnomalyService.enrich_anomaly",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/anomalies/services/anomaly_service.py",
        symbol="AnomalyService.process_candle_closed",
        detail="list[dict[str, object]]",
    ),
    ArchitectureViolation(
        path="src/apps/anomalies/services/anomaly_service.py",
        symbol="AnomalyService.scan_market_structure",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/anomalies/services/anomaly_service.py",
        symbol="AnomalyService.scan_sector_synchrony",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/control_plane/services.py",
        symbol="TopologyObservabilityService.build_overview",
        detail="dict[str, Any]",
    ),
    ArchitectureViolation(
        path="src/apps/control_plane/services.py",
        symbol="TopologyService.build_graph",
        detail="dict[str, Any]",
    ),
    ArchitectureViolation(
        path="src/apps/control_plane/services.py",
        symbol="TopologyService.build_snapshot",
        detail="dict[str, Any]",
    ),
    ArchitectureViolation(
        path="src/apps/cross_market/services.py",
        symbol="CrossMarketLeaderDetectionResult.to_summary",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/cross_market/services.py",
        symbol="CrossMarketRelationUpdateResult.to_summary",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/cross_market/services.py",
        symbol="CrossMarketSectorMomentumResult.to_summary",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/cross_market/services.py",
        symbol="CrossMarketService.process_event",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/hypothesis_engine/services/weight_update_service.py",
        symbol="WeightUpdateService.apply_to_evaluation",
        detail="tuple[str, dict[str, object]] | None",
    ),
    ArchitectureViolation(
        path="src/apps/market_data/services.py",
        symbol="MarketDataHistorySyncService.sync_coin_history_backfill",
        detail="dict[str, int | str]",
    ),
    ArchitectureViolation(
        path="src/apps/market_data/services.py",
        symbol="MarketDataHistorySyncService.sync_coin_latest_history",
        detail="dict[str, int | str]",
    ),
    ArchitectureViolation(
        path="src/apps/market_structure/services.py",
        symbol="MarketStructureService.ingest_manual_snapshots",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/market_structure/services.py",
        symbol="MarketStructureService.ingest_native_webhook_payload",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/market_structure/services.py",
        symbol="MarketStructureService.poll_enabled_sources",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/market_structure/services.py",
        symbol="MarketStructureService.poll_source",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/market_structure/services.py",
        symbol="MarketStructureService.refresh_source_health",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/news/services.py",
        symbol="NewsService.poll_enabled_sources",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/news/services.py",
        symbol="NewsService.poll_source",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_bootstrap.py",
        symbol="PatternBootstrapService.bootstrap_scan",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_runtime.py",
        symbol="PatternRealtimeService.detect_incremental_signals",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_runtime.py",
        symbol="PatternRealtimeService.refresh_regime_state",
        detail="dict[str, object] | None",
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
    ArchitectureViolation(
        path="src/apps/predictions/services.py",
        symbol="PredictionCreationBatch.to_summary",
        detail="dict[str, object]",
    ),
    ArchitectureViolation(
        path="src/apps/predictions/services.py",
        symbol="PredictionEvaluationBatch.to_summary",
        detail="dict[str, object]",
    ),
)

EXPECTED_SERVICE_CONSTRUCTOR_DEPENDENCY_VIOLATIONS: tuple[ArchitectureViolation, ...] = (
    ArchitectureViolation(
        path="src/apps/control_plane/services.py",
        symbol="AuditLogService.__init__",
        detail="session: AsyncSession",
    ),
    ArchitectureViolation(
        path="src/apps/control_plane/services.py",
        symbol="EventRegistryService.__init__",
        detail="session: AsyncSession",
    ),
    ArchitectureViolation(
        path="src/apps/control_plane/services.py",
        symbol="TopologyObservabilityService.__init__",
        detail="session: AsyncSession",
    ),
    ArchitectureViolation(
        path="src/apps/control_plane/services.py",
        symbol="TopologyService.__init__",
        detail="session: AsyncSession",
    ),
)

EXPECTED_TRANSPORT_LEAKAGE_VIOLATIONS: tuple[ArchitectureViolation, ...] = (
    ArchitectureViolation(
        path="src/apps/anomalies/services/anomaly_service.py",
        symbol="src.apps.anomalies.schemas",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/hypothesis_engine/services/prompt_service.py",
        symbol="src.apps.hypothesis_engine.schemas",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/market_data/services.py",
        symbol="src.apps.market_data.schemas",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/market_structure/services.py",
        symbol="src.apps.market_structure.schemas",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/market_structure/services.py",
        symbol="src.core.http.router_policy",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/news/services.py",
        symbol="src.apps.news.schemas",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/news/services.py",
        symbol="src.core.http.router_policy",
        detail="import",
    ),
)

EXPECTED_CROSS_DOMAIN_BOUNDARY_VIOLATIONS: tuple[ArchitectureViolation, ...] = (
    ArchitectureViolation(
        path="src/apps/cross_market/services.py",
        symbol="src.apps.market_data.repositories",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/indicators/services.py",
        symbol="src.apps.market_data.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/indicators/services.py",
        symbol="src.apps.market_data.repositories",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/market_structure/services.py",
        symbol="src.apps.market_data.models",
        detail="import",
    ),
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
        path="src/apps/patterns/task_service_runtime.py",
        symbol="src.apps.cross_market.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_runtime.py",
        symbol="src.apps.indicators.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_runtime.py",
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
    ArchitectureViolation(
        path="src/apps/predictions/services.py",
        symbol="src.apps.cross_market.models",
        detail="import",
    ),
    ArchitectureViolation(
        path="src/apps/predictions/services.py",
        symbol="src.apps.market_data.repositories",
        detail="import",
    ),
)

EXPECTED_SERVICE_MODULE_THRESHOLD_VIOLATIONS: tuple[ArchitectureViolation, ...] = (
    ArchitectureViolation(
        path="src/apps/anomalies/services/anomaly_service.py",
        symbol="AnomalyService",
        detail="class_loc=369",
    ),
    ArchitectureViolation(
        path="src/apps/anomalies/services/anomaly_service.py",
        symbol="__module__",
        detail="module_loc=412",
    ),
    ArchitectureViolation(
        path="src/apps/control_plane/services.py",
        symbol="TopologyDraftService",
        detail="class_loc=333",
    ),
    ArchitectureViolation(
        path="src/apps/control_plane/services.py",
        symbol="__module__",
        detail="module_loc=763",
    ),
    ArchitectureViolation(
        path="src/apps/control_plane/services.py",
        symbol="__module__",
        detail="service_class_count=6",
    ),
    ArchitectureViolation(
        path="src/apps/cross_market/services.py",
        symbol="CrossMarketService",
        detail="class_loc=440",
    ),
    ArchitectureViolation(
        path="src/apps/cross_market/services.py",
        symbol="__module__",
        detail="module_loc=599",
    ),
    ArchitectureViolation(
        path="src/apps/indicators/services.py",
        symbol="IndicatorAnalyticsService",
        detail="class_loc=253",
    ),
    ArchitectureViolation(
        path="src/apps/indicators/services.py",
        symbol="__module__",
        detail="module_loc=538",
    ),
    ArchitectureViolation(
        path="src/apps/market_data/services.py",
        symbol="__module__",
        detail="module_loc=619",
    ),
    ArchitectureViolation(
        path="src/apps/market_structure/services.py",
        symbol="MarketStructureService",
        detail="class_loc=554",
    ),
    ArchitectureViolation(
        path="src/apps/market_structure/services.py",
        symbol="MarketStructureSourceProvisioningService",
        detail="class_loc=498",
    ),
    ArchitectureViolation(
        path="src/apps/market_structure/services.py",
        symbol="__module__",
        detail="module_loc=1406",
    ),
    ArchitectureViolation(
        path="src/apps/news/services.py",
        symbol="__module__",
        detail="module_loc=530",
    ),
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
        path="src/apps/patterns/task_service_runtime.py",
        symbol="PatternRealtimeService",
        detail="class_loc=503",
    ),
    ArchitectureViolation(
        path="src/apps/patterns/task_service_runtime.py",
        symbol="__module__",
        detail="module_loc=533",
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
    ArchitectureViolation(
        path="src/apps/predictions/services.py",
        symbol="__module__",
        detail="module_loc=438",
    ),
)
