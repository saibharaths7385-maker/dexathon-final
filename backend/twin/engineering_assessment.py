"""Explainable, configurable engineering assessment for Phase 2.

Rules in this module are deliberately opt-in. Data-validity limits from Phase
1 are not operating limits and cannot produce engine health findings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .feature_engineering import FeatureEngineer

RuleCondition = Literal["greater_than", "less_than", "greater_or_equal", "less_or_equal"]
AssessmentStatus = Literal["NORMAL", "WARNING", "CRITICAL", "NOT_ASSESSED"]
SEVERITY_ORDER = {"NORMAL": 0, "WARNING": 1, "CRITICAL": 2, "NOT_ASSESSED": 3}


@dataclass(frozen=True)
class EngineeringRule:
    """An approved operating rule supplied by an engineering authority."""

    rule_id: str
    parameter: str
    condition: RuleCondition
    threshold: float
    severity: Literal["WARNING", "CRITICAL"]
    explanation: str
    configuration_source: str
    unit: str = ""

    def __post_init__(self) -> None:
        if not self.rule_id.strip() or not self.parameter.strip():
            raise ValueError("rule_id and parameter must not be blank")
        if not self.configuration_source.strip():
            raise ValueError("configuration_source must not be blank")


@dataclass(frozen=True)
class AssessmentConfig:
    """Explicit operating rules; empty means no operating limits are approved."""

    rules: tuple[EngineeringRule, ...] = ()


def _matches(value: float, condition: RuleCondition, threshold: float) -> bool:
    return {
        "greater_than": value > threshold,
        "less_than": value < threshold,
        "greater_or_equal": value >= threshold,
        "less_or_equal": value <= threshold,
    }[condition]


def _condition_text(rule: EngineeringRule) -> str:
    operator = {
        "greater_than": ">",
        "less_than": "<",
        "greater_or_equal": ">=",
        "less_or_equal": "<=",
    }[rule.condition]
    return f"{rule.parameter} {operator} {rule.threshold:g} {rule.unit}".strip()


def _quality_finding(parameter: str, sensor: dict[str, Any]) -> dict[str, Any]:
    status = sensor["status"]
    reason = (
        "No value was received for this parameter."
        if status == "missing"
        else "The received value failed data validation."
    )
    return {
        "rule_id": f"data_quality.{parameter}.{status}",
        "parameter": parameter,
        "condition": "data_quality",
        "severity": "NOT_ASSESSED",
        "status": "NOT_ASSESSED",
        "measurement": sensor.get("value"),
        "unit": sensor.get("unit", ""),
        "evidence": {"sensor_status": status, "source": sensor.get("source")},
        "explanation": f"{parameter} is not assessed: {reason}",
        "configuration_source": "Phase 1 sensor validation",
    }


def assess_features(
    processed: dict[str, Any],
    *,
    config: AssessmentConfig | None = None,
) -> dict[str, Any]:
    """Assess one Phase 1 result without scoring health or making predictions."""

    configured = config or AssessmentConfig()
    rules_by_parameter: dict[str, list[EngineeringRule]] = {}
    for rule in configured.rules:
        rules_by_parameter.setdefault(rule.parameter, []).append(rule)

    findings: list[dict[str, Any]] = []
    sensors = processed.get("sensors", {})
    features = processed.get("features", {})
    parameters = {
        "rpm": sensors.get("rpm"),
        "engine_temperature": sensors.get("engine_temperature"),
        "battery_voltage": sensors.get("battery_voltage"),
        "electrical_current": sensors.get("electrical_current"),
        "fuel_percent": sensors.get("fuel_percent"),
        "rpm_change_per_second": {"status": "valid" if features.get("rpm_change_per_second") is not None else "missing",
                                  "value": features.get("rpm_change_per_second"), "unit": "rpm/s"},
        "temperature_change_per_second": {"status": "valid" if features.get("temperature_change_per_second") is not None else "missing",
                                          "value": features.get("temperature_change_per_second"), "unit": "°C/s"},
        "fuel_consumption_rate_percent_per_second": {
            "status": "valid" if features.get("fuel_consumption_rate_percent_per_second") is not None else "missing",
            "value": features.get("fuel_consumption_rate_percent_per_second"), "unit": "%/s",
        },
    }

    parameters_to_evaluate = (
        set(rules_by_parameter) if configured.rules else set(parameters)
    )
    for parameter, sensor in parameters.items():
        if parameter not in parameters_to_evaluate:
            continue
        if not isinstance(sensor, dict):
            continue
        applicable = rules_by_parameter.get(parameter, [])
        if sensor.get("status") != "valid":
            findings.append(_quality_finding(parameter, sensor))
            continue
        if not applicable:
            findings.append({
                "rule_id": f"not_assessed.{parameter}",
                "parameter": parameter,
                "condition": "operating_limit_unavailable",
                "severity": "NOT_ASSESSED",
                "status": "NOT_ASSESSED",
                "measurement": sensor["value"],
                "unit": sensor.get("unit", ""),
                "evidence": {"sensor_status": "valid"},
                "explanation": f"{parameter} was received, but no approved operating limit is configured.",
                "configuration_source": "No approved engineering configuration",
            })
            continue
        for rule in applicable:
            triggered = _matches(sensor["value"], rule.condition, rule.threshold)
            findings.append({
                "rule_id": rule.rule_id,
                "parameter": parameter,
                "condition": _condition_text(rule),
                "severity": rule.severity if triggered else "NORMAL",
                "status": rule.severity if triggered else "NORMAL",
                "measurement": sensor["value"],
                "threshold": rule.threshold,
                "unit": rule.unit or sensor.get("unit", ""),
                "evidence": {
                    "sensor_status": "valid",
                    "condition_met": triggered,
                    "source": sensor.get("source"),
                },
                "explanation": (
                    rule.explanation
                    if triggered
                    else f"{parameter} did not meet the configured condition {_condition_text(rule)}."
                ),
                "configuration_source": rule.configuration_source,
            })

    if not processed.get("accepted", False):
        status: AssessmentStatus = "NOT_ASSESSED"
        assessment_reason = "Telemetry metadata or container validation failed."
    elif any(item["status"] == "CRITICAL" for item in findings):
        status = "CRITICAL"
        assessment_reason = "At least one approved engineering rule was classified as critical."
    elif any(item["status"] == "WARNING" for item in findings):
        status = "WARNING"
        assessment_reason = "At least one approved engineering rule was classified as warning."
    elif findings and all(item["status"] == "NORMAL" for item in findings):
        status = "NORMAL"
        assessment_reason = "All configured engineering rules were evaluated without a finding."
    else:
        status = "NOT_ASSESSED"
        assessment_reason = "One or more required parameters lack approved operating limits or valid data."

    return {
        "status": status,
        "reason": assessment_reason,
        "timestamp": processed.get("timestamp"),
        "aircraft_id": processed.get("aircraft_id"),
        "mission_id": processed.get("mission_id"),
        "scenario_id": processed.get("scenario_id"),
        "scenario_context": processed.get("scenario_context"),
        "findings": findings,
        "explainability": {
            "evaluated_parameters": sorted(parameters),
            "rules_applied": [rule.rule_id for rule in configured.rules],
            "unavailable_information": [
                item["parameter"]
                for item in findings
                if item["status"] == "NOT_ASSESSED"
            ],
            "limitation": "Engineering rules only; no numerical health score, probability, anomaly model, or RUL.",
        },
        "data_quality": processed.get("data_quality"),
        "raw_telemetry": processed.get("raw_telemetry"),
    }


def assess_frame(
    frame: dict[str, Any],
    *,
    config: AssessmentConfig | None = None,
    feature_engineer: FeatureEngineer | None = None,
) -> dict[str, Any]:
    """Preprocess, feature-engineer, and assess one normalized frame."""

    engineer = feature_engineer or FeatureEngineer()
    processed = engineer.process(frame)
    result = assess_features(processed, config=config)
    result["features"] = processed.get("features")
    result["feature_quality"] = processed.get("feature_quality")
    return result
