"""Transparent Phase 5 health status and optional experimental scoring.

No calibrated scoring parameters are present in this repository. By default
this module returns ``NOT_CALIBRATED`` and no numerical score. An experimental
configuration may be supplied for demonstrations; its formula and provenance
are returned in the result and it must not be interpreted as a validated health
measure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

HealthCategory = Literal[
    "HEALTHY",
    "DEGRADED",
    "WARNING",
    "CRITICAL",
    "INSUFFICIENT_DATA",
    "NOT_CALIBRATED",
]


@dataclass(frozen=True)
class ExperimentalScoringConfig:
    """Explicit demonstration weights; not an approved engineering model."""

    critical_penalty: float
    warning_penalty: float
    high_trend_penalty: float
    moderate_trend_penalty: float
    source: str
    rationale: str
    algorithm_version: str = "experimental-health-score-1.0"

    def __post_init__(self) -> None:
        values = (
            self.critical_penalty,
            self.warning_penalty,
            self.high_trend_penalty,
            self.moderate_trend_penalty,
        )
        if any(value < 0 or value > 100 for value in values):
            raise ValueError("experimental penalties must be between 0 and 100")
        if not self.source.strip() or not self.rationale.strip():
            raise ValueError("source and rationale must not be blank")


def _findings(assessment: dict[str, Any]) -> list[dict[str, Any]]:
    values = assessment.get("findings", [])
    return values if isinstance(values, list) else []


def _trends(trend_assessments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return trend_assessments if isinstance(trend_assessments, list) else []


def _quality(assessment: dict[str, Any]) -> dict[str, Any]:
    value = assessment.get("data_quality")
    return value if isinstance(value, dict) else {}


def _missing_measurements(assessment: dict[str, Any]) -> list[str]:
    quality = _quality(assessment)
    missing = quality.get("missing_sensors", [])
    invalid = quality.get("invalid_sensors", [])
    return [
        *[str(item) for item in missing],
        *[f"{item} (invalid)" for item in invalid],
    ]


def _evidence_summary(
    assessment: dict[str, Any],
    trend_assessments: list[dict[str, Any]],
) -> dict[str, Any]:
    findings = _findings(assessment)
    trends = _trends(trend_assessments)
    return {
        "engineering_rule_findings": findings,
        "historical_trend_indicators": trends,
        "data_quality": _quality(assessment),
        "missing_measurements": _missing_measurements(assessment),
        "assessment_coverage": {
            "engineering_findings": len(findings),
            "trend_indicators": len(trends),
            "normal_engineering_findings": sum(
                item.get("status") == "NORMAL" for item in findings
            ),
            "not_assessed_engineering_findings": sum(
                item.get("status") == "NOT_ASSESSED" for item in findings
            ),
        },
    }


def _supported_data(assessment: dict[str, Any], trends: list[dict[str, Any]]) -> bool:
    quality = _quality(assessment)
    if quality.get("invalid_sensors") or quality.get("missing_sensors"):
        return False
    if assessment.get("accepted") is False:
        return False
    return any(
        item.get("risk_category") not in {"INSUFFICIENT_DATA", "NOT_ASSESSED"}
        for item in trends
    ) or bool(_findings(assessment))


def _category(
    assessment: dict[str, Any],
    trends: list[dict[str, Any]],
    *,
    calibrated: bool,
) -> HealthCategory:
    if not _supported_data(assessment, trends):
        return "INSUFFICIENT_DATA"
    findings = _findings(assessment)
    if any(item.get("status") == "CRITICAL" for item in findings):
        return "CRITICAL"
    if any(item.get("risk_category") == "HIGH" for item in trends):
        return "WARNING"
    if any(item.get("status") == "WARNING" for item in findings) or any(
        item.get("risk_category") == "MODERATE" for item in trends
    ):
        return "WARNING"
    if not calibrated:
        return "NOT_CALIBRATED"
    return "HEALTHY"


def _experimental_score(
    assessment: dict[str, Any],
    trends: list[dict[str, Any]],
    config: ExperimentalScoringConfig,
) -> tuple[float | None, list[dict[str, Any]]]:
    if not _supported_data(assessment, trends):
        return None, []
    contributions: list[dict[str, Any]] = []
    score = 100.0
    for finding in _findings(assessment):
        status = finding.get("status")
        penalty = {
            "CRITICAL": config.critical_penalty,
            "WARNING": config.warning_penalty,
        }.get(status, 0)
        if penalty:
            score -= penalty
            contributions.append({
                "source": "engineering_rule",
                "rule_id": finding.get("rule_id"),
                "parameter": finding.get("parameter"),
                "penalty": penalty,
            })
    for trend in trends:
        risk = trend.get("risk_category")
        penalty = {
            "HIGH": config.high_trend_penalty,
            "MODERATE": config.moderate_trend_penalty,
        }.get(risk, 0)
        if penalty:
            score -= penalty
            contributions.append({
                "source": "historical_trend",
                "assessment_id": trend.get("assessment_id"),
                "parameter": trend.get("parameter"),
                "penalty": penalty,
            })
    return round(max(0.0, min(100.0, score)), 2), contributions


def assess_health(
    assessment: dict[str, Any],
    trend_assessments: list[dict[str, Any]] | None = None,
    *,
    experimental_config: ExperimentalScoringConfig | None = None,
) -> dict[str, Any]:
    """Combine existing evidence without claiming calibration or prediction."""

    trends = trend_assessments or []
    calibrated = experimental_config is not None
    category = _category(assessment, trends, calibrated=calibrated)
    score, contributions = (
        _experimental_score(assessment, trends, experimental_config)
        if experimental_config
        else (None, [])
    )
    if category == "NOT_CALIBRATED" and experimental_config:
        category = "DEGRADED" if contributions else "HEALTHY"
    evidence = _evidence_summary(assessment, trends)
    provenance = {
        "synthetic": assessment.get("raw_telemetry", {}).get("synthetic")
        if isinstance(assessment.get("raw_telemetry"), dict)
        else None,
        "source": assessment.get("raw_telemetry", {}).get("provenance")
        if isinstance(assessment.get("raw_telemetry"), dict)
        else None,
    }
    if experimental_config:
        algorithm_version = experimental_config.algorithm_version
        calibration_status = "EXPERIMENTAL_UNCALIBRATED"
        explanation = (
            "An experimental score was calculated from configured rule and trend "
            "penalties. It is not calibrated against labelled engine outcomes."
        )
        configuration = {
            "source": experimental_config.source,
            "rationale": experimental_config.rationale,
            "weights": {
                "critical_penalty": experimental_config.critical_penalty,
                "warning_penalty": experimental_config.warning_penalty,
                "high_trend_penalty": experimental_config.high_trend_penalty,
                "moderate_trend_penalty": experimental_config.moderate_trend_penalty,
            },
        }
    else:
        algorithm_version = "health-status-only-1.0"
        calibration_status = "NOT_CALIBRATED"
        explanation = (
            "No approved scoring parameters or labelled validation data are "
            "available; no numerical health score is presented."
        )
        configuration = {
            "source": "No approved scoring configuration",
            "rationale": "Avoid unsupported numerical health claims.",
        }
    if category == "INSUFFICIENT_DATA":
        explanation = (
            "Health status is insufficient because required telemetry evidence is "
            "missing, invalid, or lacks adequate historical coverage."
        )
    return {
        "status": category,
        "health_score": score,
        "score_kind": "EXPERIMENTAL" if score is not None else "UNAVAILABLE",
        "calibration_status": calibration_status,
        "algorithm_version": algorithm_version,
        "aircraft_id": assessment.get("aircraft_id"),
        "mission_id": assessment.get("mission_id"),
        "timestamp": assessment.get("timestamp"),
        "scenario_id": assessment.get("scenario_id"),
        "scenario_context": assessment.get("scenario_context"),
        "explanation": explanation,
        "contributing_parameters": sorted({
            item.get("parameter")
            for item in evidence["engineering_rule_findings"]
            if item.get("parameter")
        } | {
            item.get("parameter")
            for item in evidence["historical_trend_indicators"]
            if item.get("parameter")
        }),
        "evidence": evidence,
        "score_contributions": contributions,
        "configuration": configuration,
        "provenance": {
            **provenance,
            "assessment_kind": "health_status_and_explainability",
        },
        "limitations": [
            "No calibrated health score is available.",
            "No Isolation Forest, failure probability, or RUL is used.",
            "Environmental scenario context is preserved but does not modify thresholds.",
        ],
    }
