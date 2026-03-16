"""event control plane foundation

Revision ID: 20260312_000029
Revises: 20260312_000028
Create Date: 2026-03-12 23:20:00.000000
"""


from alembic import op
import sqlalchemy as sa


revision = "20260312_000029"
down_revision = "20260312_000028"
branch_labels = None
depends_on = None


FILTER_FIELDS = ["symbol", "timeframe", "exchange", "confidence", "metadata"]
SUPPORTED_SCOPES = ["global", "domain", "symbol", "exchange", "timeframe", "environment"]
DEFAULT_ENVIRONMENT = "*"

EVENT_DEFINITIONS: list[dict[str, object]] = [
    {
        "event_type": "candle_inserted",
        "display_name": "Candle Inserted",
        "domain": "market_data",
        "description": "A base candle was inserted into the canonical candle store.",
        "is_control_event": False,
    },
    {
        "event_type": "candle_closed",
        "display_name": "Candle Closed",
        "domain": "market_data",
        "description": "A candle completed and is ready for downstream analysis.",
        "is_control_event": False,
    },
    {
        "event_type": "indicator_updated",
        "display_name": "Indicator Updated",
        "domain": "indicators",
        "description": "Indicator cache and metrics were refreshed for a candle.",
        "is_control_event": False,
    },
    {
        "event_type": "analysis_requested",
        "display_name": "Analysis Requested",
        "domain": "patterns",
        "description": "The scheduler requested pattern analysis for a coin and timeframe.",
        "is_control_event": False,
    },
    {
        "event_type": "pattern_detected",
        "display_name": "Pattern Detected",
        "domain": "patterns",
        "description": "A concrete market pattern was detected.",
        "is_control_event": False,
    },
    {
        "event_type": "pattern_cluster_detected",
        "display_name": "Pattern Cluster Detected",
        "domain": "patterns",
        "description": "A higher-level pattern cluster was detected.",
        "is_control_event": False,
    },
    {
        "event_type": "pattern_disabled",
        "display_name": "Pattern Disabled",
        "domain": "patterns",
        "description": "Pattern success logic disabled a pattern emission.",
        "is_control_event": False,
    },
    {
        "event_type": "pattern_degraded",
        "display_name": "Pattern Degraded",
        "domain": "patterns",
        "description": "Pattern success logic degraded a pattern confidence.",
        "is_control_event": False,
    },
    {
        "event_type": "pattern_boosted",
        "display_name": "Pattern Boosted",
        "domain": "patterns",
        "description": "Pattern success logic boosted a pattern confidence.",
        "is_control_event": False,
    },
    {
        "event_type": "market_regime_changed",
        "display_name": "Market Regime Changed",
        "domain": "indicators",
        "description": "The inferred market regime changed for a coin/timeframe.",
        "is_control_event": False,
    },
    {
        "event_type": "market_cycle_changed",
        "display_name": "Market Cycle Changed",
        "domain": "indicators",
        "description": "The inferred market cycle phase changed.",
        "is_control_event": False,
    },
    {
        "event_type": "signal_created",
        "display_name": "Signal Created",
        "domain": "signals",
        "description": "A tradable or analytical signal was created.",
        "is_control_event": False,
    },
    {
        "event_type": "decision_generated",
        "display_name": "Decision Generated",
        "domain": "signals",
        "description": "An investment decision was generated.",
        "is_control_event": False,
    },
    {
        "event_type": "correlation_updated",
        "display_name": "Correlation Updated",
        "domain": "cross_market",
        "description": "Cross-market correlation state was updated.",
        "is_control_event": False,
    },
    {
        "event_type": "sector_rotation_detected",
        "display_name": "Sector Rotation Detected",
        "domain": "cross_market",
        "description": "A leading sector changed in sector momentum calculations.",
        "is_control_event": False,
    },
    {
        "event_type": "market_leader_detected",
        "display_name": "Market Leader Detected",
        "domain": "cross_market",
        "description": "A market leader breakout or breakdown was detected.",
        "is_control_event": False,
    },
    {
        "event_type": "prediction_confirmed",
        "display_name": "Prediction Confirmed",
        "domain": "predictions",
        "description": "A cross-market prediction was confirmed.",
        "is_control_event": False,
    },
    {
        "event_type": "prediction_failed",
        "display_name": "Prediction Failed",
        "domain": "predictions",
        "description": "A cross-market prediction failed or expired.",
        "is_control_event": False,
    },
    {
        "event_type": "anomaly_detected",
        "display_name": "Anomaly Detected",
        "domain": "anomalies",
        "description": "An anomaly was created by the anomaly detection subsystem.",
        "is_control_event": False,
    },
    {
        "event_type": "news_item_ingested",
        "display_name": "News Item Ingested",
        "domain": "news",
        "description": "A news item entered the normalization pipeline.",
        "is_control_event": False,
    },
    {
        "event_type": "news_item_normalized",
        "display_name": "News Item Normalized",
        "domain": "news",
        "description": "A news item completed normalization.",
        "is_control_event": False,
    },
    {
        "event_type": "news_symbol_correlation_updated",
        "display_name": "News Symbol Correlation Updated",
        "domain": "news",
        "description": "A normalized news item was correlated to one or more symbols.",
        "is_control_event": False,
    },
    {
        "event_type": "portfolio_position_opened",
        "display_name": "Portfolio Position Opened",
        "domain": "portfolio",
        "description": "A portfolio position was opened.",
        "is_control_event": False,
    },
    {
        "event_type": "portfolio_position_closed",
        "display_name": "Portfolio Position Closed",
        "domain": "portfolio",
        "description": "A portfolio position was closed.",
        "is_control_event": False,
    },
    {
        "event_type": "portfolio_rebalanced",
        "display_name": "Portfolio Rebalanced",
        "domain": "portfolio",
        "description": "A portfolio position was increased or reduced.",
        "is_control_event": False,
    },
    {
        "event_type": "portfolio_balance_updated",
        "display_name": "Portfolio Balance Updated",
        "domain": "portfolio",
        "description": "Exchange balance sync updated a tracked balance.",
        "is_control_event": False,
    },
    {
        "event_type": "portfolio_position_changed",
        "display_name": "Portfolio Position Changed",
        "domain": "portfolio",
        "description": "Portfolio position state changed after sync or execution.",
        "is_control_event": False,
    },
    {
        "event_type": "coin_auto_watch_enabled",
        "display_name": "Coin Auto Watch Enabled",
        "domain": "portfolio",
        "description": "Portfolio sync auto-enabled a coin for tracking.",
        "is_control_event": False,
    },
    {
        "event_type": "market_structure_snapshot_ingested",
        "display_name": "Market Structure Snapshot Ingested",
        "domain": "market_structure",
        "description": "A market structure snapshot was stored.",
        "is_control_event": False,
    },
    {
        "event_type": "market_structure_source_health_updated",
        "display_name": "Market Structure Source Health Updated",
        "domain": "market_structure",
        "description": "A market structure source health snapshot changed.",
        "is_control_event": False,
    },
    {
        "event_type": "market_structure_source_alerted",
        "display_name": "Market Structure Source Alerted",
        "domain": "market_structure",
        "description": "A market structure source emitted an alert.",
        "is_control_event": False,
    },
    {
        "event_type": "market_structure_source_quarantined",
        "display_name": "Market Structure Source Quarantined",
        "domain": "market_structure",
        "description": "A market structure source entered quarantine.",
        "is_control_event": False,
    },
    {
        "event_type": "market_structure_source_deleted",
        "display_name": "Market Structure Source Deleted",
        "domain": "market_structure",
        "description": "A market structure source was deleted.",
        "is_control_event": False,
    },
    {
        "event_type": "hypothesis_created",
        "display_name": "Hypothesis Created",
        "domain": "hypothesis",
        "description": "The hypothesis engine created a new hypothesis.",
        "is_control_event": False,
    },
    {
        "event_type": "hypothesis_evaluated",
        "display_name": "Hypothesis Evaluated",
        "domain": "hypothesis",
        "description": "A hypothesis evaluation completed.",
        "is_control_event": False,
    },
    {
        "event_type": "ai_insight",
        "display_name": "AI Insight",
        "domain": "hypothesis",
        "description": "The hypothesis engine emitted a narrative insight.",
        "is_control_event": False,
    },
    {
        "event_type": "ai_weights_updated",
        "display_name": "AI Weights Updated",
        "domain": "hypothesis",
        "description": "Bayesian weight updates were published by the AI engine.",
        "is_control_event": False,
    },
    {
        "event_type": "control.route_created",
        "display_name": "Control Route Created",
        "domain": "control_plane",
        "description": "A control-plane route was created.",
        "is_control_event": True,
    },
    {
        "event_type": "control.route_updated",
        "display_name": "Control Route Updated",
        "domain": "control_plane",
        "description": "A control-plane route was updated.",
        "is_control_event": True,
    },
    {
        "event_type": "control.route_status_changed",
        "display_name": "Control Route Status Changed",
        "domain": "control_plane",
        "description": "A control-plane route status changed.",
        "is_control_event": True,
    },
    {
        "event_type": "control.topology_published",
        "display_name": "Control Topology Published",
        "domain": "control_plane",
        "description": "A new topology version was published.",
        "is_control_event": True,
    },
    {
        "event_type": "control.cache_invalidated",
        "display_name": "Control Cache Invalidated",
        "domain": "control_plane",
        "description": "A topology cache invalidation was requested.",
        "is_control_event": True,
    },
]

EVENT_CONSUMERS: list[dict[str, object]] = [
    {
        "consumer_key": "indicator_workers",
        "display_name": "Indicator Workers",
        "domain": "indicators",
        "description": "Refreshes indicator cache and emits indicator updates.",
        "implementation_key": "iris.runtime.streams.workers._handle_indicator_event",
        "delivery_mode": "worker",
        "delivery_stream": "iris:deliveries:indicator_workers",
        "supports_shadow": False,
        "compatible_event_types_json": ["candle_closed"],
    },
    {
        "consumer_key": "analysis_scheduler_workers",
        "display_name": "Analysis Scheduler Workers",
        "domain": "patterns",
        "description": "Schedules pattern analysis from fresh indicator updates.",
        "implementation_key": "iris.runtime.streams.workers._handle_analysis_scheduler_event",
        "delivery_mode": "worker",
        "delivery_stream": "iris:deliveries:analysis_scheduler_workers",
        "supports_shadow": False,
        "compatible_event_types_json": ["indicator_updated"],
    },
    {
        "consumer_key": "pattern_workers",
        "display_name": "Pattern Workers",
        "domain": "patterns",
        "description": "Runs pattern detection and emits derived pattern signals.",
        "implementation_key": "iris.runtime.streams.workers._handle_pattern_event",
        "delivery_mode": "worker",
        "delivery_stream": "iris:deliveries:pattern_workers",
        "supports_shadow": False,
        "compatible_event_types_json": ["analysis_requested"],
    },
    {
        "consumer_key": "regime_workers",
        "display_name": "Regime Workers",
        "domain": "indicators",
        "description": "Updates regime and cycle state from indicator events.",
        "implementation_key": "iris.runtime.streams.workers._handle_regime_event",
        "delivery_mode": "worker",
        "delivery_stream": "iris:deliveries:regime_workers",
        "supports_shadow": False,
        "compatible_event_types_json": ["indicator_updated"],
    },
    {
        "consumer_key": "decision_workers",
        "display_name": "Decision Workers",
        "domain": "signals",
        "description": "Evaluates investment decisions and final signals.",
        "implementation_key": "iris.runtime.streams.workers._handle_decision_event",
        "delivery_mode": "worker",
        "delivery_stream": "iris:deliveries:decision_workers",
        "supports_shadow": False,
        "compatible_event_types_json": [
            "pattern_detected",
            "pattern_cluster_detected",
            "market_regime_changed",
            "market_cycle_changed",
            "signal_created",
        ],
    },
    {
        "consumer_key": "signal_fusion_workers",
        "display_name": "Signal Fusion Workers",
        "domain": "signals",
        "description": "Fuses signals, news and correlation state into market decisions.",
        "implementation_key": "iris.runtime.streams.workers._handle_fusion_event",
        "delivery_mode": "worker",
        "delivery_stream": "iris:deliveries:signal_fusion_workers",
        "supports_shadow": False,
        "compatible_event_types_json": [
            "pattern_detected",
            "signal_created",
            "market_regime_changed",
            "correlation_updated",
            "news_symbol_correlation_updated",
        ],
    },
    {
        "consumer_key": "cross_market_workers",
        "display_name": "Cross Market Workers",
        "domain": "cross_market",
        "description": "Refreshes cross-market relations, leadership and predictions.",
        "implementation_key": "iris.runtime.streams.workers._handle_cross_market_event",
        "delivery_mode": "worker",
        "delivery_stream": "iris:deliveries:cross_market_workers",
        "supports_shadow": False,
        "compatible_event_types_json": ["candle_closed", "indicator_updated"],
    },
    {
        "consumer_key": "anomaly_workers",
        "display_name": "Anomaly Workers",
        "domain": "anomalies",
        "description": "Runs anomaly detection from fresh candles.",
        "implementation_key": "iris.runtime.streams.workers._handle_anomaly_event",
        "delivery_mode": "worker",
        "delivery_stream": "iris:deliveries:anomaly_workers",
        "supports_shadow": False,
        "compatible_event_types_json": ["candle_closed"],
    },
    {
        "consumer_key": "anomaly_sector_workers",
        "display_name": "Anomaly Sector Workers",
        "domain": "anomalies",
        "description": "Runs enrichment and sector scans for severe anomalies.",
        "implementation_key": "iris.runtime.streams.workers._handle_anomaly_sector_event",
        "delivery_mode": "worker",
        "delivery_stream": "iris:deliveries:anomaly_sector_workers",
        "supports_shadow": False,
        "compatible_event_types_json": ["anomaly_detected"],
    },
    {
        "consumer_key": "news_normalization_workers",
        "display_name": "News Normalization Workers",
        "domain": "news",
        "description": "Normalizes ingested news items.",
        "implementation_key": "iris.runtime.streams.workers._handle_news_normalization_event",
        "delivery_mode": "worker",
        "delivery_stream": "iris:deliveries:news_normalization_workers",
        "supports_shadow": False,
        "compatible_event_types_json": ["news_item_ingested"],
    },
    {
        "consumer_key": "news_correlation_workers",
        "display_name": "News Correlation Workers",
        "domain": "news",
        "description": "Correlates normalized news items to tracked assets.",
        "implementation_key": "iris.runtime.streams.workers._handle_news_correlation_event",
        "delivery_mode": "worker",
        "delivery_stream": "iris:deliveries:news_correlation_workers",
        "supports_shadow": False,
        "compatible_event_types_json": ["news_item_normalized"],
    },
    {
        "consumer_key": "portfolio_workers",
        "display_name": "Portfolio Workers",
        "domain": "portfolio",
        "description": "Transforms decisions and balance syncs into portfolio actions.",
        "implementation_key": "iris.runtime.streams.workers._handle_portfolio_event",
        "delivery_mode": "worker",
        "delivery_stream": "iris:deliveries:portfolio_workers",
        "supports_shadow": False,
        "compatible_event_types_json": [
            "decision_generated",
            "market_regime_changed",
            "portfolio_balance_updated",
            "portfolio_position_changed",
        ],
    },
    {
        "consumer_key": "hypothesis_workers",
        "display_name": "Hypothesis Workers",
        "domain": "hypothesis",
        "description": "Creates AI hypotheses from selected upstream events.",
        "implementation_key": "iris.runtime.streams.workers._handle_hypothesis_event",
        "delivery_mode": "worker",
        "delivery_stream": "iris:deliveries:hypothesis_workers",
        "supports_shadow": False,
        "compatible_event_types_json": [
            "signal_created",
            "anomaly_detected",
            "decision_generated",
            "market_regime_changed",
            "portfolio_position_changed",
            "portfolio_balance_updated",
        ],
        "settings_json": {"feature_flag": "enable_hypothesis_engine"},
    },
]

EVENT_ROUTES: list[dict[str, object]] = [
    {"event_type": "candle_closed", "consumer_key": "indicator_workers"},
    {"event_type": "indicator_updated", "consumer_key": "analysis_scheduler_workers"},
    {"event_type": "analysis_requested", "consumer_key": "pattern_workers"},
    {"event_type": "indicator_updated", "consumer_key": "regime_workers"},
    {"event_type": "pattern_detected", "consumer_key": "decision_workers"},
    {"event_type": "pattern_cluster_detected", "consumer_key": "decision_workers"},
    {"event_type": "market_regime_changed", "consumer_key": "decision_workers"},
    {"event_type": "market_cycle_changed", "consumer_key": "decision_workers"},
    {"event_type": "signal_created", "consumer_key": "decision_workers"},
    {"event_type": "pattern_detected", "consumer_key": "signal_fusion_workers"},
    {"event_type": "signal_created", "consumer_key": "signal_fusion_workers"},
    {"event_type": "market_regime_changed", "consumer_key": "signal_fusion_workers"},
    {"event_type": "correlation_updated", "consumer_key": "signal_fusion_workers"},
    {"event_type": "news_symbol_correlation_updated", "consumer_key": "signal_fusion_workers"},
    {"event_type": "candle_closed", "consumer_key": "cross_market_workers"},
    {"event_type": "indicator_updated", "consumer_key": "cross_market_workers"},
    {"event_type": "candle_closed", "consumer_key": "anomaly_workers"},
    {"event_type": "anomaly_detected", "consumer_key": "anomaly_sector_workers"},
    {"event_type": "news_item_ingested", "consumer_key": "news_normalization_workers"},
    {"event_type": "news_item_normalized", "consumer_key": "news_correlation_workers"},
    {"event_type": "decision_generated", "consumer_key": "portfolio_workers"},
    {"event_type": "market_regime_changed", "consumer_key": "portfolio_workers"},
    {"event_type": "portfolio_balance_updated", "consumer_key": "portfolio_workers"},
    {"event_type": "portfolio_position_changed", "consumer_key": "portfolio_workers"},
    {"event_type": "signal_created", "consumer_key": "hypothesis_workers"},
    {"event_type": "anomaly_detected", "consumer_key": "hypothesis_workers"},
    {"event_type": "decision_generated", "consumer_key": "hypothesis_workers"},
    {"event_type": "market_regime_changed", "consumer_key": "hypothesis_workers"},
    {"event_type": "portfolio_position_changed", "consumer_key": "hypothesis_workers"},
    {"event_type": "portfolio_balance_updated", "consumer_key": "hypothesis_workers"},
]


def _route_key(event_type: str, consumer_key: str) -> str:
    return f"{event_type}:{consumer_key}:global:*:{DEFAULT_ENVIRONMENT}"


def upgrade() -> None:
    op.create_table(
        "event_definitions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("is_control_event", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("payload_schema_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("routing_hints_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_event_definitions_event_type ON event_definitions (event_type)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_event_definitions_domain_control "
        "ON event_definitions (domain, is_control_event)"
    )

    op.create_table(
        "event_consumers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("consumer_key", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("domain", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("implementation_key", sa.String(length=255), nullable=False),
        sa.Column("delivery_mode", sa.String(length=32), nullable=False, server_default=sa.text("'worker'")),
        sa.Column("delivery_stream", sa.String(length=255), nullable=False),
        sa.Column("supports_shadow", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("compatible_event_types_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("supported_filter_fields_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("supported_scopes_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("settings_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_event_consumers_consumer_key ON event_consumers (consumer_key)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_event_consumers_domain_mode ON event_consumers (domain, delivery_mode)")

    op.create_table(
        "topology_config_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'published'")),
        sa.Column("summary", sa.String(length=255), nullable=False),
        sa.Column("published_by", sa.String(length=128), nullable=False, server_default=sa.text("'system'")),
        sa.Column("snapshot_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_topology_config_versions_version_number "
        "ON topology_config_versions (version_number)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_topology_config_versions_status_created_desc "
        "ON topology_config_versions (status, created_at)"
    )

    op.create_table(
        "topology_drafts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("access_mode", sa.String(length=16), nullable=False, server_default=sa.text("'observe'")),
        sa.Column("base_version_id", sa.Integer(), sa.ForeignKey("topology_config_versions.id", ondelete="SET NULL")),
        sa.Column("created_by", sa.String(length=128), nullable=False, server_default=sa.text("'system'")),
        sa.Column("applied_version_id", sa.Integer(), sa.ForeignKey("topology_config_versions.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_topology_drafts_status_updated_desc ON topology_drafts (status, updated_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_topology_drafts_base_version ON topology_drafts (base_version_id)")

    op.create_table(
        "event_routes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("route_key", sa.String(length=255), nullable=False),
        sa.Column("event_definition_id", sa.Integer(), sa.ForeignKey("event_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consumer_id", sa.Integer(), sa.ForeignKey("event_consumers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("scope_type", sa.String(length=32), nullable=False, server_default=sa.text("'global'")),
        sa.Column("scope_value", sa.String(length=128), nullable=True),
        sa.Column("environment", sa.String(length=32), nullable=False, server_default=sa.text("'*'")),
        sa.Column("filters_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("throttle_config_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("shadow_config_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("notes", sa.String(length=255), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("system_managed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_event_routes_route_key ON event_routes (route_key)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_event_routes_status_scope_env "
        "ON event_routes (status, scope_type, environment)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_event_routes_event_consumer "
        "ON event_routes (event_definition_id, consumer_id)"
    )

    op.create_table(
        "topology_draft_changes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("draft_id", sa.BigInteger(), sa.ForeignKey("topology_drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("change_type", sa.String(length=64), nullable=False),
        sa.Column("target_route_key", sa.String(length=255), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_by", sa.String(length=128), nullable=False, server_default=sa.text("'system'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_topology_draft_changes_draft_target "
        "ON topology_draft_changes (draft_id, target_route_key)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_topology_draft_changes_type_created_desc "
        "ON topology_draft_changes (change_type, created_at)"
    )

    op.create_table(
        "event_route_audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("route_id", sa.Integer(), sa.ForeignKey("event_routes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("route_key_snapshot", sa.String(length=255), nullable=False),
        sa.Column("draft_id", sa.BigInteger(), sa.ForeignKey("topology_drafts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("topology_version_id", sa.Integer(), sa.ForeignKey("topology_config_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False, server_default=sa.text("'system'")),
        sa.Column("actor_mode", sa.String(length=16), nullable=False, server_default=sa.text("'control'")),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("before_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("after_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("context_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_event_route_audit_logs_route_created_desc "
        "ON event_route_audit_logs (route_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_event_route_audit_logs_action_created_desc "
        "ON event_route_audit_logs (action, created_at)"
    )

    bind = op.get_bind()

    event_definitions_table = sa.table(
        "event_definitions",
        sa.column("id", sa.Integer),
        sa.column("event_type", sa.String),
        sa.column("display_name", sa.String),
        sa.column("domain", sa.String),
        sa.column("description", sa.String),
        sa.column("is_control_event", sa.Boolean),
        sa.column("payload_schema_json", sa.JSON),
        sa.column("routing_hints_json", sa.JSON),
    )
    event_consumers_table = sa.table(
        "event_consumers",
        sa.column("id", sa.Integer),
        sa.column("consumer_key", sa.String),
        sa.column("display_name", sa.String),
        sa.column("domain", sa.String),
        sa.column("description", sa.String),
        sa.column("implementation_key", sa.String),
        sa.column("delivery_mode", sa.String),
        sa.column("delivery_stream", sa.String),
        sa.column("supports_shadow", sa.Boolean),
        sa.column("compatible_event_types_json", sa.JSON),
        sa.column("supported_filter_fields_json", sa.JSON),
        sa.column("supported_scopes_json", sa.JSON),
        sa.column("settings_json", sa.JSON),
    )
    event_routes_table = sa.table(
        "event_routes",
        sa.column("id", sa.Integer),
        sa.column("route_key", sa.String),
        sa.column("event_definition_id", sa.Integer),
        sa.column("consumer_id", sa.Integer),
        sa.column("status", sa.String),
        sa.column("scope_type", sa.String),
        sa.column("scope_value", sa.String),
        sa.column("environment", sa.String),
        sa.column("filters_json", sa.JSON),
        sa.column("throttle_config_json", sa.JSON),
        sa.column("shadow_config_json", sa.JSON),
        sa.column("notes", sa.String),
        sa.column("priority", sa.Integer),
        sa.column("system_managed", sa.Boolean),
    )
    topology_versions_table = sa.table(
        "topology_config_versions",
        sa.column("id", sa.Integer),
        sa.column("version_number", sa.Integer),
        sa.column("status", sa.String),
        sa.column("summary", sa.String),
        sa.column("published_by", sa.String),
        sa.column("snapshot_json", sa.JSON),
    )
    audit_table = sa.table(
        "event_route_audit_logs",
        sa.column("route_id", sa.Integer),
        sa.column("route_key_snapshot", sa.String),
        sa.column("draft_id", sa.BigInteger),
        sa.column("topology_version_id", sa.Integer),
        sa.column("action", sa.String),
        sa.column("actor", sa.String),
        sa.column("actor_mode", sa.String),
        sa.column("reason", sa.String),
        sa.column("before_json", sa.JSON),
        sa.column("after_json", sa.JSON),
        sa.column("context_json", sa.JSON),
    )

    bind.execute(
        event_definitions_table.insert(),
        [
            {
                **event_definition,
                "payload_schema_json": {},
                "routing_hints_json": {"filter_fields": FILTER_FIELDS},
            }
            for event_definition in EVENT_DEFINITIONS
        ],
    )
    bind.execute(
        event_consumers_table.insert(),
        [
            {
                **consumer,
                "supported_filter_fields_json": FILTER_FIELDS,
                "supported_scopes_json": SUPPORTED_SCOPES,
                "settings_json": consumer.get("settings_json", {}),
            }
            for consumer in EVENT_CONSUMERS
        ],
    )

    event_definition_id_by_type = {
        row.event_type: int(row.id)
        for row in bind.execute(sa.select(event_definitions_table.c.id, event_definitions_table.c.event_type))
    }
    consumer_id_by_key = {
        row.consumer_key: int(row.id)
        for row in bind.execute(sa.select(event_consumers_table.c.id, event_consumers_table.c.consumer_key))
    }

    route_rows: list[dict[str, object]] = [
        {
            "route_key": _route_key(str(route["event_type"]), str(route["consumer_key"])),
            "event_definition_id": event_definition_id_by_type[str(route["event_type"])],
            "consumer_id": consumer_id_by_key[str(route["consumer_key"])],
            "status": "active",
            "scope_type": "global",
            "scope_value": None,
            "environment": DEFAULT_ENVIRONMENT,
            "filters_json": {},
            "throttle_config_json": {},
            "shadow_config_json": {},
            "notes": "Bootstrapped from legacy runtime router",
            "priority": 100,
            "system_managed": True,
        }
        for route in EVENT_ROUTES
    ]
    bind.execute(event_routes_table.insert(), route_rows)

    route_id_by_key = {
        row.route_key: int(row.id)
        for row in bind.execute(sa.select(event_routes_table.c.id, event_routes_table.c.route_key))
    }
    event_definitions_snapshot = [
        {
            "event_type": str(event["event_type"]),
            "display_name": str(event["display_name"]),
            "domain": str(event["domain"]),
            "is_control_event": bool(event["is_control_event"]),
        }
        for event in EVENT_DEFINITIONS
    ]
    consumers_snapshot = [
        {
            "consumer_key": str(consumer["consumer_key"]),
            "display_name": str(consumer["display_name"]),
            "domain": str(consumer["domain"]),
            "delivery_stream": str(consumer["delivery_stream"]),
            "compatible_event_types": (
                [str(item) for item in consumer["compatible_event_types_json"]]
                if isinstance(consumer["compatible_event_types_json"], list)
                else []
            ),
        }
        for consumer in EVENT_CONSUMERS
    ]
    routes_snapshot = [
        {
            "route_key": row["route_key"],
            "event_type": route["event_type"],
            "consumer_key": route["consumer_key"],
            "status": "active",
            "scope_type": "global",
            "environment": DEFAULT_ENVIRONMENT,
            "filters": {},
        }
        for route, row in zip(EVENT_ROUTES, route_rows, strict=True)
    ]
    version_snapshot = {
        "version_number": 1,
        "summary": "Bootstrapped from legacy Redis stream worker topology",
        "events": event_definitions_snapshot,
        "consumers": consumers_snapshot,
        "routes": routes_snapshot,
    }
    version_id = bind.execute(
        topology_versions_table.insert().returning(topology_versions_table.c.id),
        [
            {
                "version_number": 1,
                "status": "published",
                "summary": "Bootstrapped from legacy Redis stream worker topology",
                "published_by": "system",
                "snapshot_json": version_snapshot,
            }
        ],
    ).scalar_one()

    bind.execute(
        audit_table.insert(),
        [
            {
                "route_id": route_id_by_key[row["route_key"]],
                "route_key_snapshot": row["route_key"],
                "draft_id": None,
                "topology_version_id": int(version_id),
                "action": "bootstrapped",
                "actor": "system",
                "actor_mode": "control",
                "reason": "legacy_runtime_router_import",
                "before_json": {},
                "after_json": {
                    "event_type": route["event_type"],
                    "consumer_key": route["consumer_key"],
                    "status": "active",
                    "scope_type": "global",
                    "environment": DEFAULT_ENVIRONMENT,
                },
                "context_json": {
                    "source": "legacy_runtime_router",
                    "migration_revision": revision,
                },
            }
            for route, row in zip(EVENT_ROUTES, route_rows, strict=True)
        ],
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_event_route_audit_logs_action_created_desc")
    op.execute("DROP INDEX IF EXISTS ix_event_route_audit_logs_route_created_desc")
    op.drop_table("event_route_audit_logs")

    op.execute("DROP INDEX IF EXISTS ix_topology_draft_changes_type_created_desc")
    op.execute("DROP INDEX IF EXISTS ix_topology_draft_changes_draft_target")
    op.drop_table("topology_draft_changes")

    op.execute("DROP INDEX IF EXISTS ix_event_routes_event_consumer")
    op.execute("DROP INDEX IF EXISTS ix_event_routes_status_scope_env")
    op.execute("DROP INDEX IF EXISTS ux_event_routes_route_key")
    op.drop_table("event_routes")

    op.execute("DROP INDEX IF EXISTS ix_topology_drafts_base_version")
    op.execute("DROP INDEX IF EXISTS ix_topology_drafts_status_updated_desc")
    op.drop_table("topology_drafts")

    op.execute("DROP INDEX IF EXISTS ix_topology_config_versions_status_created_desc")
    op.execute("DROP INDEX IF EXISTS ux_topology_config_versions_version_number")
    op.drop_table("topology_config_versions")

    op.execute("DROP INDEX IF EXISTS ix_event_consumers_domain_mode")
    op.execute("DROP INDEX IF EXISTS ux_event_consumers_consumer_key")
    op.drop_table("event_consumers")

    op.execute("DROP INDEX IF EXISTS ix_event_definitions_domain_control")
    op.execute("DROP INDEX IF EXISTS ux_event_definitions_event_type")
    op.drop_table("event_definitions")
