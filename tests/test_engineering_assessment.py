import pytest

from backend.twin.engineering_assessment import (
    AssessmentConfig,
    EngineeringRule,
    assess_frame,
)
from backend.twin.laptop1 import normalize_telemetry_frame


def frame(**updates):
    result = {
        "protocol": 1,
        "seq": 1,
        "aircraft_id": "EAGLE_EYE_MINI",
        "mission_id": "MISSION-DEMO",
        "scenario": "urban",
        "phase": "cruise",
        "timestamp": "2026-11-05T00:00:00Z",
        "flight": {},
        "propulsion": {
            "engine_rpm": 4800,
            "engine_temp_c": 190,
            "battery_voltage": 14.2,
            "current_a": 12.3,
            "fuel_percent": 74,
        },
        "environment": {"temperature_c": 28, "wind_speed_mps": 5},
        "faults": [],
        "mission": {},
    }
    result.update(updates)
    return normalize_telemetry_frame(result)


def rules():
    return AssessmentConfig(rules=(
        EngineeringRule("rpm.high", "rpm", "greater_than", 5500, "WARNING",
                         "RPM exceeds the approved operating limit.", "approved-test-config", "rpm"),
        EngineeringRule("temp.high", "engine_temperature", "greater_than", 220, "CRITICAL",
                         "Engine temperature exceeds the approved operating limit.", "approved-test-config", "°C"),
    ))


def test_normal_telemetry_with_configured_rules_is_explainable():
    result = assess_frame(frame(), config=rules())
    assert result["status"] == "NORMAL"
    assert result["scenario_id"] == "urban"
    assert {item["rule_id"] for item in result["findings"]} == {"rpm.high", "temp.high"}
    assert all(item["configuration_source"] == "approved-test-config" for item in result["findings"])
    assert result["raw_telemetry"]["propulsion"]["engine_temp_c"] == 190


def test_high_temperature_and_rpm_are_classified_with_approved_rules():
    result = assess_frame(
        frame(propulsion={"engine_rpm": 5600, "engine_temp_c": 230,
                           "battery_voltage": 14.2, "current_a": 12.3, "fuel_percent": 74}),
        config=rules(),
    )
    assert result["status"] == "CRITICAL"
    assert {item["rule_id"] for item in result["findings"] if item["status"] != "NORMAL"} == {
        "rpm.high", "temp.high"
    }


@pytest.mark.parametrize("field,parameter", [
    ("engine_temp_c", "engine_temperature"),
    ("engine_rpm", "rpm"),
])
def test_missing_values_are_not_healthy(field, parameter):
    propulsion = frame()["propulsion"]
    del propulsion[field]
    if field == "engine_rpm":
        propulsion.pop("rpm", None)
    if field == "engine_temp_c":
        propulsion.pop("temperature_c", None)
    result = assess_frame({**frame(), "propulsion": propulsion}, config=rules())
    finding = next(item for item in result["findings"] if item["parameter"] == parameter)
    assert result["status"] == "NOT_ASSESSED"
    assert finding["status"] == "NOT_ASSESSED"


def test_invalid_sensor_value_is_reported_as_not_assessed():
    result = assess_frame(
        frame(propulsion={"engine_rpm": "invalid", "engine_temp_c": 190,
                           "battery_voltage": 14.2, "current_a": 12.3, "fuel_percent": 74}),
        config=rules(),
    )
    assert result["status"] == "NOT_ASSESSED"
    assert any(item["parameter"] == "rpm" and item["status"] == "NOT_ASSESSED"
               for item in result["findings"])


def test_motor_temperature_is_not_engine_temperature():
    result = assess_frame(
        frame(
            aircraft_id="RQ11B",
            propulsion={"motor_rpm": 5100, "motor_temp_c": 61, "battery_voltage": 15.4},
        ),
        config=rules(),
    )
    finding = next(item for item in result["findings"] if item["parameter"] == "engine_temperature")
    assert finding["status"] == "NOT_ASSESSED"
    assert "engine temperature" not in finding["evidence"]


def test_unknown_scenario_is_preserved_without_threshold_changes():
    result = assess_frame(frame(scenario="volcanic_unknown"), config=rules())
    assert result["scenario_id"] == "volcanic_unknown"
    assert result["scenario_context"]["recognized"] is False
    assert result["scenario_context"]["policy_status"] == "context_only"


def test_no_approved_limits_returns_not_assessed():
    result = assess_frame(frame())
    assert result["status"] == "NOT_ASSESSED"
    assert all(item["status"] == "NOT_ASSESSED" for item in result["findings"])
    assert result["explainability"]["unavailable_information"]


def test_multiple_simultaneous_warnings_and_trend_explanation():
    config = AssessmentConfig(rules=(
        EngineeringRule("rpm.trend", "rpm_change_per_second", "greater_than", 5, "WARNING",
                         "RPM is increasing faster than approved.", "approved-trend-config", "rpm/s"),
        EngineeringRule("temp.trend", "temperature_change_per_second", "greater_than", 1, "WARNING",
                         "Temperature is increasing faster than approved.", "approved-trend-config", "°C/s"),
    ))
    from backend.twin.feature_engineering import FeatureEngineer
    engineer = FeatureEngineer()
    engineer.process(frame())
    result = assess_frame(
        frame(timestamp="2026-11-05T00:00:01Z",
              propulsion={"engine_rpm": 4810, "engine_temp_c": 192,
                          "battery_voltage": 14.2, "current_a": 12.3, "fuel_percent": 74}),
        config=config, feature_engineer=engineer,
    )
    assert result["status"] == "WARNING"
    assert {item["rule_id"] for item in result["findings"] if item["status"] == "WARNING"} == {
        "rpm.trend", "temp.trend"
    }
    assert all(item["evidence"]["condition_met"] for item in result["findings"]
               if item["status"] == "WARNING")
