import pytest

from backend.twin.feature_engineering import FeatureEngineer
from backend.twin.laptop1 import normalize_telemetry_frame
from backend.twin.telemetry_preprocessing import preprocess_normalized_frame


def frame(**updates):
    result = {
        "protocol": 1,
        "seq": 1,
        "aircraft_id": "EAGLE_EYE_MINI",
        "mission_id": "MISSION-DEMO",
        "scenario": "desert",
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
        "environment": {"temperature_c": 28, "dust_level": 0.1},
        "faults": [],
        "mission": {},
    }
    result.update(updates)
    return normalize_telemetry_frame(result)


def raw_frame(**updates):
    result = {
        "protocol": 1,
        "seq": 1,
        "aircraft_id": "EAGLE_EYE_MINI",
        "mission_id": "MISSION-DEMO",
        "scenario": "desert",
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
        "environment": {"temperature_c": 28, "dust_level": 0.1},
        "faults": [],
        "mission": {},
    }
    result.update(updates)
    return result


def test_valid_telemetry_preserves_raw_and_scenario_context():
    original = frame()
    result = preprocess_normalized_frame(original)
    assert result["accepted"] is True
    assert result["raw_telemetry"] == original
    assert result["scenario_id"] == "desert"
    assert result["scenario_context"]["policy_status"] == "context_only"
    assert result["sensors"]["engine_temperature"]["value"] == 190
    assert result["environment"]["temperature_c"] == 28


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("engine_rpm", None),
        ("engine_temp_c", None),
        ("battery_voltage", "not-a-number"),
        ("current_a", float("inf")),
        ("fuel_percent", -1),
        ("fuel_percent", 101),
    ],
)
def test_missing_null_invalid_and_physically_invalid_values_are_distinguished(field, value):
    propulsion = raw_frame()["propulsion"]
    propulsion[field] = value
    result = preprocess_normalized_frame(
        normalize_telemetry_frame({**raw_frame(), "propulsion": propulsion})
    )
    key = {
        "engine_rpm": "rpm",
        "engine_temp_c": "engine_temperature",
        "battery_voltage": "battery_voltage",
        "current_a": "electrical_current",
        "fuel_percent": "fuel_percent",
    }[field]
    assert result["accepted"] is True
    assert result["sensors"][key]["status"] == "invalid"


def test_missing_sensor_is_not_replaced_with_zero():
    propulsion = raw_frame()["propulsion"]
    del propulsion["engine_rpm"]
    result = preprocess_normalized_frame(
        normalize_telemetry_frame({**raw_frame(), "propulsion": propulsion})
    )
    assert result["sensors"]["rpm"]["status"] == "missing"
    assert result["sensors"]["rpm"]["value"] is None


def test_motor_temperature_is_not_promoted_to_engine_temperature():
    result = preprocess_normalized_frame(
        frame(
            aircraft_id="RQ11B",
            propulsion={"motor_rpm": 5100, "motor_temp_c": 61, "battery_voltage": 15.4},
        )
    )
    assert result["sensors"]["engine_temperature"]["status"] == "missing"
    assert result["sensors"]["engine_temperature"]["note"].startswith("motor")


@pytest.mark.parametrize(
    "patch",
    [{"scenario": None}, {"scenario": ""}, {"timestamp": "2026-11-05T00:00:00"}],
)
def test_missing_or_malformed_metadata_rejects_without_throwing(patch):
    result = preprocess_normalized_frame({**frame(), **patch})
    assert result["accepted"] is False
    assert result["raw_telemetry"] is not None
    assert result["errors"]


def test_out_of_order_timestamps_do_not_create_delta_features():
    engineer = FeatureEngineer()
    first = frame()
    second = frame(timestamp="2026-11-04T23:59:59Z")
    engineer.process(first)
    result = engineer.process(second)
    assert result["feature_quality"]["has_consecutive_frame"] is False
    assert result["features"]["rpm_change_per_second"] is None


def test_features_use_consecutive_frames_and_rolling_history():
    engineer = FeatureEngineer(window_size=3)
    first = engineer.process(frame())
    second = engineer.process(
        frame(
            timestamp="2026-11-05T00:00:01Z",
            propulsion={
                "engine_rpm": 4810,
                "engine_temp_c": 191,
                "battery_voltage": 14.0,
                "current_a": 12.4,
                "fuel_percent": 73,
            },
        )
    )
    third = engineer.process(
        frame(
            timestamp="2026-11-05T00:00:02Z",
            propulsion={
                "engine_rpm": 4830,
                "engine_temp_c": 193,
                "battery_voltage": 14.1,
                "current_a": 12.5,
                "fuel_percent": 72,
            },
        )
    )
    assert first["features"]["rpm_change_per_second"] is None
    assert second["features"]["rpm_change_per_second"] == 10
    assert second["features"]["fuel_consumption_rate_percent_per_second"] == 1
    assert third["features"]["rpm_change_per_second"] == 20
    assert third["features"]["rolling"]["rpm_moving_average"] == pytest.approx(4805)
    assert third["features"]["rolling"]["voltage_variation_v"] == pytest.approx(0.1)
