from backend.twin.feature_engineering import FeatureEngineer
from backend.twin.historical_trend_analysis import HistoricalTrendAnalyzer, TrendRiskConfig
from backend.twin.laptop1 import normalize_telemetry_frame
from backend.twin.telemetry_preprocessing import preprocess_normalized_frame


def raw_frame(
    *,
    timestamp="2026-11-05T00:00:00Z",
    aircraft_id="EAGLE_EYE_MINI",
    mission_id="MISSION-DEMO",
    scenario="urban",
    rpm=4800,
    temperature=190,
    voltage=14.2,
    current=12.3,
    fuel=74,
    synthetic=True,
):
    return {
        "protocol": 1,
        "seq": 1,
        "aircraft_id": aircraft_id,
        "mission_id": mission_id,
        "scenario": scenario,
        "phase": "cruise",
        "timestamp": timestamp,
        "flight": {},
        "propulsion": {
            "engine_rpm": rpm,
            "engine_temp_c": temperature,
            "battery_voltage": voltage,
            "current_a": current,
            "fuel_percent": fuel,
        },
        "environment": {"temperature_c": 28, "dust_level": 0.1},
        "faults": [],
        "mission": {},
        "synthetic": synthetic,
        "provenance": "synthetic-test-telemetry",
    }


def add(analyzer, engineer, frame, assessment=None):
    processed = engineer.process(normalize_telemetry_frame(frame))
    return analyzer.add(processed, assessment=assessment)


def results(analyzer, aircraft="EAGLE_EYE_MINI", mission="MISSION-DEMO"):
    return analyzer.analyze(aircraft_id=aircraft, mission_id=mission)


def test_stable_history_is_low_but_explicitly_experimental():
    analyzer, engineer = HistoricalTrendAnalyzer(), FeatureEngineer()
    for second in range(3):
        assert add(
            analyzer,
            engineer,
            raw_frame(timestamp=f"2026-11-05T00:00:0{second}Z"),
        ) == "accepted"
    temperature = next(item for item in results(analyzer) if item["parameter"] == "engine_temperature_c")
    assert temperature["risk_category"] == "LOW"
    assert temperature["provenance"]["assessment_kind"] == "experimental_trend_indicator"
    assert temperature["provenance"]["synthetic"] is True
    assert "failure probability" in " ".join(temperature["limitations"])


def test_increasing_temperature_trend_is_high_with_actual_evidence():
    config = TrendRiskConfig(high_temperature_slope=1.0, moderate_temperature_slope=0.5)
    analyzer, engineer = HistoricalTrendAnalyzer(config=config), FeatureEngineer()
    for second, value in enumerate((190, 192, 194)):
        add(analyzer, engineer, raw_frame(
            timestamp=f"2026-11-05T00:00:0{second}Z", temperature=value
        ))
    result = next(item for item in results(analyzer) if item["parameter"] == "engine_temperature_c")
    assert result["risk_category"] == "HIGH"
    assert result["observed_trend"]["last_value"] == 194
    assert result["data_sufficiency"]["accepted_observations"] == 3


def test_rpm_deterioration_and_voltage_variation_are_detected():
    analyzer = HistoricalTrendAnalyzer(config=TrendRiskConfig(high_voltage_variation=0.5))
    engineer = FeatureEngineer()
    for second, (rpm, voltage) in enumerate(((4800, 14.2), (4750, 13.0), (4700, 14.2))):
        add(analyzer, engineer, raw_frame(
            timestamp=f"2026-11-05T00:00:0{second}Z", rpm=rpm, voltage=voltage
        ))
    assessed = {item["parameter"]: item for item in results(analyzer)}
    assert assessed["rpm"]["risk_category"] == "HIGH"
    assert assessed["battery_voltage_v"]["risk_category"] == "HIGH"
    assert assessed["battery_voltage_v"]["observed_trend"]["variation"] > 0.5


def test_fuel_consumption_trend_is_based_on_consecutive_features():
    analyzer, engineer = HistoricalTrendAnalyzer(), FeatureEngineer()
    for second, fuel in enumerate((74, 73, 72, 71)):
        add(analyzer, engineer, raw_frame(
            timestamp=f"2026-11-05T00:00:0{second}Z", fuel=fuel
        ))
    result = next(
        item for item in results(analyzer)
        if item["parameter"] == "fuel_consumption_rate_percent_per_second"
    )
    assert result["risk_category"] == "HIGH"
    assert result["observed_trend"]["first_value"] == 1


def test_repeated_engineering_warnings_include_rule_ids_and_duration():
    analyzer, engineer = HistoricalTrendAnalyzer(), FeatureEngineer()
    assessment = {"findings": [{"rule_id": "temp.high", "status": "WARNING"}]}
    for second in range(4):
        add(
            analyzer,
            engineer,
            raw_frame(timestamp=f"2026-11-05T00:00:0{second}Z"),
            assessment=assessment,
        )
    result = next(item for item in results(analyzer) if item["parameter"] == "engineering_warnings")
    assert result["risk_category"] == "HIGH"
    assert result["observed_trend"]["warning_count"] == 4
    assert result["observed_trend"]["rule_ids"] == ["temp.high"]
    assert result["data_sufficiency"]["duration_seconds"] == 3


def test_insufficient_history_and_missing_sensor_are_not_assessed():
    analyzer, engineer = HistoricalTrendAnalyzer(), FeatureEngineer()
    add(analyzer, engineer, raw_frame())
    assessed = {item["parameter"]: item for item in results(analyzer)}
    assert assessed["engine_temperature_c"]["risk_category"] == "INSUFFICIENT_DATA"
    assert assessed["engine_temperature_c"]["data_sufficiency"]["sufficient"] is False

    missing = raw_frame(timestamp="2026-11-05T00:00:01Z")
    del missing["propulsion"]["engine_temp_c"]
    add(analyzer, engineer, missing)
    assessed = {item["parameter"]: item for item in results(analyzer)}
    assert assessed["engine_temperature_c"]["risk_category"] == "INSUFFICIENT_DATA"


def test_invalid_timestamp_duplicate_and_out_of_order_do_not_enter_history():
    analyzer, engineer = HistoricalTrendAnalyzer(), FeatureEngineer()
    first = raw_frame()
    assert add(analyzer, engineer, first) == "accepted"
    assert add(analyzer, engineer, first) == "duplicate_timestamp"
    assert add(analyzer, engineer, raw_frame(timestamp="2026-11-04T23:59:59Z")) == "out_of_order"
    assert add(analyzer, engineer, raw_frame(timestamp="not-a-timestamp")) == "invalid_timestamp"
    assert len(analyzer._streams[("EAGLE_EYE_MINI", "MISSION-DEMO")]) == 1
    assert {item["reason"] for item in analyzer.rejections} == {
        "duplicate_timestamp", "out_of_order", "invalid_timestamp"
    }


def test_aircraft_and_mission_histories_are_separate():
    analyzer, engineer = HistoricalTrendAnalyzer(), FeatureEngineer()
    add(analyzer, engineer, raw_frame(temperature=190))
    add(analyzer, engineer, raw_frame(
        timestamp="2026-11-05T00:00:01Z", aircraft_id="OTHER", temperature=250
    ))
    add(analyzer, engineer, raw_frame(
        timestamp="2026-11-05T00:00:02Z", mission_id="OTHER-MISSION", temperature=250
    ))
    assert results(analyzer)[0]["data_sufficiency"]["accepted_observations"] == 1
    assert results(analyzer, aircraft="OTHER")[0]["data_sufficiency"]["accepted_observations"] == 1
    assert results(analyzer, mission="OTHER-MISSION")[0]["data_sufficiency"]["accepted_observations"] == 1


def test_scenario_metadata_is_preserved_without_environmental_adjustment():
    analyzer, engineer = HistoricalTrendAnalyzer(), FeatureEngineer()
    for second in range(3):
        add(analyzer, engineer, raw_frame(
            timestamp=f"2026-11-05T00:00:0{second}Z", scenario="volcanic"
        ))
    result = results(analyzer)[0]
    assert result["scenario_id"] == "volcanic"
    assert result["historical_evidence"]["scenario_ids"] == ["volcanic"]


def test_unavailable_fault_labels_are_declared_as_a_limitation():
    analyzer, engineer = HistoricalTrendAnalyzer(), FeatureEngineer()
    for second in range(3):
        add(analyzer, engineer, raw_frame(
            timestamp=f"2026-11-05T00:00:0{second}Z"
        ))
    assert any("labelled engine-fault" in item for item in results(analyzer)[0]["limitations"])
