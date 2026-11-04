"""Phase 3 rules use synthetic fixtures, never claimed as a live Laptop 1 feed."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.twin.decision_support import laptop1_recommendations, twin_recommendations
from backend.twin.laptop1 import HANDSHAKE, InvalidTelemetryFrame, Laptop1TelemetryClient, validate_telemetry_frame
from backend.twin.model import EngineState, advance
from backend.twin.schemas import Controls
from backend.twin.service import TwinService

NOW = datetime(2026, 11, 4, 10, 40, tzinfo=timezone.utc)


def bridge(**updates):
    frame = {"protocol": 1, "seq": 7, "aircraft_id": "TEST-AIRCRAFT",
        "mission_id": "TEST-MISSION", "scenario": "coastal", "phase": "cruise",
        "timestamp": NOW.isoformat(), "flight": {}, "propulsion": {},
        "environment": {}, "faults": [], "mission": {}}
    frame.update(updates)
    return {"status": "connected", "latest_frame": frame,
        "last_received_at": NOW.isoformat(), "last_error": None}


def details(records):
    return [record["recommendation_details"] for record in records]


@pytest.fixture
def service():
    instance = TwinService(":memory:")
    instance.observed_at = NOW
    yield instance
    instance.close()


def snapshot(service):
    result = service.snapshot()
    result["quality"]["status"] = "live"
    return result


@pytest.mark.parametrize("scenario,expected", [
    ("nominal", "v2.routine_condition_inspection"),
    ("engine_degradation", "v2.engine_degradation"),
    ("sensor_bias", "v2.sensor_bias"), ("fuel_leak", "v2.fuel_leak"),
    ("compressor_fouling", "v2.compressor_fouling"),
    ("engine_overheating", "v2.thermal_overload"), ("cooling_loss", "v2.thermal_overload"),
    ("oil_leak", "v2.lubrication_pressure_loss"),
    ("sensor_drift", "v2.routine_condition_inspection"),
    ("bearing_wear", "v2.rotating_assembly_anomaly"),
    ("fuel_restriction", "v2.fuel_delivery_anomaly"),
])
def test_every_existing_scenario_has_traceable_advisories(service, scenario, expected):
    service.controls = Controls(scenario=scenario)
    for _ in range(120):
        advance(service.state, service.controls, 1)
    sample = snapshot(service)
    records = twin_recommendations(sample, NOW)
    assert records == twin_recommendations(sample, NOW)
    assert expected in [item["rule_id"] for item in details(records)]
    for record in records:
        assert record["scenario"] == scenario
        item = record["recommendation_details"]
        assert item["evidence"] and item["rule_basis"] and item["recommended_action"]
        assert item["advisory_only"] and item["timestamp"] == NOW.isoformat()
        assert item["sample_timestamp"] == NOW.isoformat()
        for sample in item["evidence"]:
            if sample["key"] in {"egt", "cht", "oil_temperature"}:
                assert sample["unit"] == "°C"


@pytest.mark.parametrize("key,boundary,exceed,rule", [
    ("oil_pressure", 2.5, 2.49, "lubrication_pressure_loss"),
    ("cht", 220, 220.01, "thermal_overload"),
    ("oil_temperature", 120, 120.01, "thermal_overload"),
    ("vibration", 5, 5.01, "rotating_assembly_anomaly"),
    ("egt", 820, 820.01, "power_or_combustion_deviation"),
])
def test_existing_strict_threshold_boundaries(service, key, boundary, exceed, rule):
    service.state.sensors[key] = boundary
    assert "v2." + rule not in [item["rule_id"] for item in details(twin_recommendations(snapshot(service), NOW))]
    service.state.sensors[key] = exceed
    assert "v2." + rule in [item["rule_id"] for item in details(twin_recommendations(snapshot(service), NOW))]


def test_all_concurrent_faults_are_retained(service):
    service.state.sensors.update(oil_pressure=1.0, cht=240, vibration=8)
    ids = {item["rule_id"] for item in details(twin_recommendations(snapshot(service), NOW))}
    assert {"v2.lubrication_pressure_loss", "v2.thermal_overload", "v2.rotating_assembly_anomaly", "v2.mission_review"} <= ids


def test_external_samples_do_not_inherit_selected_simulation_fault(service):
    service.sample_source = "telemetry"
    service.controls = Controls(source="telemetry", scenario="fuel_leak")
    service.state.fault_elapsed_seconds = 120
    records = twin_recommendations(snapshot(service), NOW)
    assert records[0]["scenario"] == "unreported"
    assert details(records)[0]["rule_id"] == "v2.routine_condition_inspection"
    assert all(item["rule_id"] != "v2.fuel_leak" for item in details(records))


@pytest.mark.parametrize("quality", ["waiting", "stale", "paused"])
def test_twin_quality_suppresses_fault_rules(service, quality):
    sample = snapshot(service)
    sample["quality"]["status"] = quality
    assert [item["rule_id"] for item in details(twin_recommendations(sample, NOW))] == ["twin.data_quality"]


@pytest.mark.parametrize("offset,expected", [(2, "protocol1.no_reported_faults"), (2.001, "protocol1.data_quality"), (-2.001, "protocol1.data_quality")])
def test_laptop_source_timestamp_freshness(offset, expected):
    state = bridge(timestamp=(NOW - timedelta(seconds=offset)).isoformat())
    assert details(laptop1_recommendations(state, NOW))[0]["rule_id"] == expected


@pytest.mark.parametrize("patch", [
    {"latest_frame": None}, {"status": "disconnected"}, {"status": "stale"},
    {"last_error": "invalid_frame"}, {"last_received_at": None},
    {"last_received_at": (NOW - timedelta(seconds=3)).isoformat()},
])
def test_laptop_missing_stale_invalid_never_reports_normal(patch):
    state = bridge()
    state.update(patch)
    assert details(laptop1_recommendations(state, NOW))[0]["rule_id"] == "protocol1.data_quality"


def test_unknown_scenario_and_raw_faults_do_not_invent_engineering_limits():
    faults = [{"code": "UNKNOWN", "severity": "critical", "description": "Source text"}]
    state = bridge(scenario="unverified-environment", faults=faults,
        propulsion={"engine_temp_c": 9999, "battery_voltage": 1})
    original = copy.deepcopy(state)
    record = laptop1_recommendations(state, NOW)[0]
    item = record["recommendation_details"]
    assert item["severity"] == "warning"  # review urgency; does not assign aircraft severity
    assert next(e["value"] for e in item["evidence"] if e["key"] == "faults") == faults
    assert "unverified" in item["limitation"]
    assert state == original
    assert record["scenario"] == "unverified-environment"


def test_unsupported_payload_is_quality_advisory():
    assert details(laptop1_recommendations(bridge(faults="unknown"), NOW))[0]["quality"] == "unsupported_payload"


def test_changed_source_fault_cannot_inherit_prior_approval(service):
    now = datetime.now(timezone.utc).isoformat()
    state = bridge(timestamp=now, faults=[{"code": "FIRST"}])
    state["last_received_at"] = now
    first = next(r for r in service.scenario_recommendations(state)["recommendations"] if r["source"] == "LAPTOP1_PROTOCOL1")
    service.decide_recommendation(first["recommendation_id"], "approved", "First fault reviewed.")
    state["latest_frame"]["faults"] = [{"code": "SECOND"}]
    second = next(r for r in service.scenario_recommendations(state)["recommendations"] if r["source"] == "LAPTOP1_PROTOCOL1")
    assert second["status"] == "pending"
    assert second["recommendation_id"] != first["recommendation_id"]


def test_repeated_or_out_of_order_frames_do_not_refresh_receipt():
    client = Laptop1TelemetryClient("ws://unused")
    frame = bridge()["latest_frame"]
    assert client._accept_frame(json.dumps(frame))
    receipt = client.snapshot()["last_received_at"]
    for update in ({}, {"seq": 6}, {"seq": 8, "timestamp": (NOW - timedelta(seconds=1)).isoformat()}):
        assert not client._accept_frame(json.dumps({**frame, **update}))
        assert client.snapshot()["last_received_at"] == receipt
        assert client.snapshot()["raw_latest_frame"] == frame
    assert client._accept_frame(json.dumps({**frame, "seq": 8, "timestamp": (NOW + timedelta(seconds=1)).isoformat()}))
    assert client.snapshot()["last_error"] is None
    assert HANDSHAKE == {"type": "hello", "client": "skynex-3d", "protocol": 1}


def test_overflow_number_rejected_without_changing_protocol():
    raw = json.dumps(bridge()["latest_frame"]).replace('"propulsion": {}', '"propulsion": {"rpm": 1e999}')
    with pytest.raises(InvalidTelemetryFrame):
        validate_telemetry_frame(raw)


def test_decisions_deduplicate_and_preserve_approved_evidence_on_restart(tmp_path):
    database = str(tmp_path / "phase3.sqlite3")
    instance = TwinService(database)
    state = bridge(timestamp=datetime.now(timezone.utc).isoformat())
    state["last_received_at"] = state["latest_frame"]["timestamp"]
    first = instance.scenario_recommendations(state)
    record = next(r for r in first["recommendations"] if r["source"] == "LAPTOP1_PROTOCOL1")
    controls, engine = copy.deepcopy(instance.controls), copy.deepcopy(instance.state)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: instance.scenario_recommendations(state), range(2)))
    assert all([r["recommendation_id"] for r in result["recommendations"]] == [r["recommendation_id"] for r in first["recommendations"]] for result in outcomes)
    instance.decide_recommendation(record["recommendation_id"], "approved", "Reviewed raw source evidence.")
    with pytest.raises(ValueError, match="already been decided"):
        instance.decide_recommendation(record["recommendation_id"], "rejected", "Duplicate")
    assert instance.controls == controls and instance.state == engine and instance.history() == []
    instance.close()
    restored = TwinService(database)
    try:
        state["latest_frame"]["seq"] += 1
        current = next(r for r in restored.scenario_recommendations(state)["recommendations"] if r["source"] == "LAPTOP1_PROTOCOL1")
        assert current["status"] == "approved"
        assert current["recommendation_details"] == record["recommendation_details"]
        assert current["current_details"]["evidence"] != record["recommendation_details"]["evidence"]
        assert len(restored.decision_history()) == len(first["recommendations"])
    finally:
        restored.close()


def test_phase3_route_uses_server_evidence_and_existing_decision_workflow(monkeypatch):
    monkeypatch.setenv("TWIN_DATABASE", ":memory:")
    monkeypatch.delenv("LAPTOP1_TELEMETRY_WS_URL", raising=False)
    with TestClient(app) as client:
        response = client.post("/api/v2/recommendations/evaluate")
        assert response.status_code == 200
        records = response.json()["recommendations"]
        record = next(r for r in records if r["source"] == "LAPTOP1_PROTOCOL1")
        assert record["current_details"]["quality"] == "missing"
        path = f"/api/v2/recommendations/{record['recommendation_id']}/decision"
        assert client.post(path, json={"status": "rejected", "operator_comment": "No live feed."}).status_code == 200
        assert client.post(path, json={"status": "approved", "operator_comment": "Duplicate"}).status_code == 409
        assert any(r["status"] == "rejected" for r in client.get("/api/v2/decisions/history").json()["history"])
