from backend.twin.engineering_assessment import AssessmentConfig, EngineeringRule, assess_frame
from backend.twin.feature_engineering import FeatureEngineer
from backend.twin.health_scoring import ExperimentalScoringConfig, assess_health
from backend.twin.historical_trend_analysis import HistoricalTrendAnalyzer
from backend.twin.laptop1 import normalize_telemetry_frame


def raw_frame(*, timestamp="2026-11-05T00:00:00Z", temperature=190, rpm=4800,
              scenario="urban", fuel=74):
    return {
        "protocol": 1, "seq": 1, "aircraft_id": "EAGLE_EYE_MINI",
        "mission_id": "MISSION-DEMO", "scenario": scenario, "phase": "cruise",
        "timestamp": timestamp, "flight": {},
        "propulsion": {"engine_rpm": rpm, "engine_temp_c": temperature,
                       "battery_voltage": 14.2, "current_a": 12.3,
                       "fuel_percent": fuel},
        "environment": {"temperature_c": 28}, "faults": [], "mission": {},
        "synthetic": True, "provenance": "synthetic-phase5-test",
    }


def rule_assessment(frame=None):
    frame = frame or raw_frame()
    config = AssessmentConfig(rules=(
        EngineeringRule("temperature.high", "engine_temperature", "greater_than",
                         220, "CRITICAL", "Approved test temperature rule.",
                         "approved-test-config", "°C"),
        EngineeringRule("rpm.high", "rpm", "greater_than", 5500, "WARNING",
                         "Approved test RPM rule.", "approved-test-config", "rpm"),
    ))
    return assess_frame(normalize_telemetry_frame(frame), config=config)


def trend_assessments():
    analyzer, engineer = HistoricalTrendAnalyzer(), FeatureEngineer()
    for second, temperature in enumerate((190, 192, 194)):
        processed = engineer.process(normalize_telemetry_frame(raw_frame(
            timestamp=f"2026-11-05T00:00:0{second}Z", temperature=temperature
        )))
        analyzer.add(processed)
    return analyzer.analyze(aircraft_id="EAGLE_EYE_MINI", mission_id="MISSION-DEMO")


def test_default_path_is_not_calibrated_and_has_no_numerical_score():
    result = assess_health(rule_assessment(), trend_assessments())
    assert result["status"] == "WARNING"
    assert result["health_score"] is None
    assert result["score_kind"] == "UNAVAILABLE"
    assert result["calibration_status"] == "NOT_CALIBRATED"
    assert "No approved scoring" in result["configuration"]["source"]


def test_missing_sensor_is_insufficient_not_healthy():
    frame = raw_frame()
    del frame["propulsion"]["engine_temp_c"]
    result = assess_health(rule_assessment(frame), [])
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["health_score"] is None
    assert "engine_temperature" in result["evidence"]["missing_measurements"]


def test_multiple_rule_findings_are_explained():
    result = assess_health(rule_assessment(raw_frame(temperature=230, rpm=5600)), [])
    assert result["status"] == "CRITICAL"
    assert {item["rule_id"] for item in result["evidence"]["engineering_rule_findings"]
            if item["status"] == "CRITICAL"} == {"temperature.high"}
    assert "engine_temperature" in result["contributing_parameters"]
    assert result["provenance"]["synthetic"] is True


def test_experimental_score_is_explicitly_configured_and_labeled():
    config = ExperimentalScoringConfig(
        critical_penalty=40, warning_penalty=10, high_trend_penalty=20,
        moderate_trend_penalty=5, source="reviewed-demo-config",
        rationale="Demonstration-only additive penalties for UI integration tests.",
    )
    result = assess_health(
        rule_assessment(raw_frame(temperature=230)),
        trend_assessments(),
        experimental_config=config,
    )
    assert result["score_kind"] == "EXPERIMENTAL"
    assert result["calibration_status"] == "EXPERIMENTAL_UNCALIBRATED"
    assert result["health_score"] == 40
    assert result["configuration"]["source"] == "reviewed-demo-config"
    assert result["score_contributions"]


def test_unconfigured_thresholds_are_not_presented_as_healthy():
    result = assess_health(
        assess_frame(normalize_telemetry_frame(raw_frame())),
        [],
    )
    assert result["status"] == "NOT_CALIBRATED"
    assert result["health_score"] is None


def test_scenario_and_explainability_are_preserved():
    result = assess_health(rule_assessment(raw_frame(scenario="volcanic")), [])
    assert result["scenario_id"] == "volcanic"
    assert result["scenario_context"]["policy_status"] == "context_only"
    for key in ("engineering_rule_findings", "historical_trend_indicators",
                "data_quality", "missing_measurements", "assessment_coverage"):
        assert key in result["evidence"]
    assert result["algorithm_version"]
    assert result["limitations"]
