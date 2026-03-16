from typing import Any

from iris.apps.anomalies.contracts import AnomalyDetectionContext, DetectorFinding
from iris.apps.anomalies.engines.contracts import EnrichedAnomalyProjection


def build_anomaly_payload(
    context: AnomalyDetectionContext,
    finding: DetectorFinding,
    source_pipeline: str,
    *,
    extra_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "metrics": dict(finding.metrics),
        "components": {name: float(value) for name, value in finding.component_scores.items()},
        "context": {
            "sector": context.sector,
            "market_regime": context.market_regime,
            "relative_to_btc": finding.explainability.get("relative_to_btc"),
            "scope": finding.scope,
            "isolated_move": finding.isolated,
            "portfolio_relevant": context.portfolio_relevant,
        },
        "explainability": {
            "what_happened": finding.explainability.get("what_happened"),
            "unusualness": finding.explainability.get("unusualness"),
            "relative_to": finding.explainability.get("relative_to"),
            "market_wide": finding.explainability.get("market_wide"),
            "affected_symbols": list(finding.affected_symbols),
        },
        "source_pipeline": source_pipeline,
        "affected_symbols": list(finding.affected_symbols),
    }
    if extra_payload:
        payload.update(extra_payload)
    return payload


def build_enriched_anomaly_projection(
    *,
    payload_json: dict[str, Any],
    portfolio_relevant: bool,
    market_wide: bool,
    enrichment_source: str,
) -> EnrichedAnomalyProjection:
    payload = dict(payload_json)
    payload_context = dict(payload.get("context", {}))
    explainability = dict(payload.get("explainability", {}))

    payload_context.update(
        {
            "portfolio_relevant": portfolio_relevant,
            "market_wide": market_wide,
        }
    )
    explainability.update(
        {
            "portfolio_impact": (
                "portfolio exposure present"
                if portfolio_relevant
                else "no open portfolio position for this instrument/timeframe"
            ),
            "market_scope": "market-wide" if market_wide else "isolated",
            "enriched_by": enrichment_source,
        }
    )

    payload["context"] = payload_context
    payload["explainability"] = explainability
    return EnrichedAnomalyProjection(
        payload_json=payload,
        portfolio_relevant=portfolio_relevant,
        market_wide=market_wide,
    )


__all__ = ["build_anomaly_payload", "build_enriched_anomaly_projection"]
