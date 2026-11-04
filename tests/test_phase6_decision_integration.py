from datetime import datetime, timezone

from backend.twin.decision_support import intelligence_recommendations
from backend.twin.service import TwinService

NOW = datetime(2026, 11, 5, 0, 50, tzinfo=timezone.utc)


def bundle(*, status="WARNING", scenario="urban", findings=None, trends=None):
    return {
        "source": "SKYNEX_PHASE6_TEST",
        "aircraft_id": "AIRCRAFT-1",
        "mission_id": "MISSION-1",
        "scenario_id": scenario,
        "engineering_assessment": {
            "aircraft_id": "AIRCRAFT-1",
            "mission_id": "MISSION-1",
            "scenario_id": scenario,
            "findings": findings or [],
            "data_quality": {"valid_sensor_count": 5, "sensor_count": 5},
            "raw_telemetry": {"synthetic": True, "provenance": "phase6-test"},
        },
        "trend_assessments": trends or [],
        "health_assessment": {
            "status": status,
            "provenance": {"synthetic": True, "source": "phase6-test"},
            "limitations": ["Experimental only."],
        },
    }


def finding(status, parameter="engine_temperature"):
    return {
        "rule_id": f"{parameter}.rule",
        "parameter": parameter,
        "status": status,
        "measurement": 230,
        "evidence": {"condition_met": True},
        "explanation": "Evidence-backed test finding.",
    }


def trend(risk="HIGH", parameter="engine_temperature_c"):
    return {
        "assessment_id": "trend-1",
        "parameter": parameter,
        "risk_category": risk,
        "explanation": "Timestamped trend evidence.",
        "data_sufficiency": {"accepted_observations": 3, "duration_seconds": 2},
        "provenance": {"synthetic": True},
    }


def test_warning_generates_evidence_backed_recommendation():
    records = intelligence_recommendations(
        bundle(findings=[finding("WARNING")]), NOW
    )
    record = records[0]
    details = record["recommendation_details"]
    assert details["severity"] == "warning"
    assert details["engineering_findings"][0]["rule_id"] == "engine_temperature.rule"
    assert details["title"]
    assert details["recommended_action"]
    assert details["algorithm_version"] == "phase6-intelligence-advisory-1.0"


def test_critical_requires_and_contains_critical_evidence():
    details = intelligence_recommendations(
        bundle(status="CRITICAL", findings=[finding("CRITICAL")]), NOW
    )[0]["recommendation_details"]
    assert details["severity"] == "critical"
    assert any(item["status"] == "CRITICAL" for item in details["engineering_findings"])
    assert "confirmed fault" in details["reason"]


def test_trend_and_insufficient_history_recommendations_are_non_predictive():
    high = intelligence_recommendations(bundle(trends=[trend("HIGH")]), NOW)
    assert high[0]["recommendation_details"]["category"] == "Historical trend inspection"
    assert "failure probability" in high[0]["recommendation_details"]["limitation"]

    insufficient = intelligence_recommendations(
        bundle(trends=[trend("INSUFFICIENT_DATA")]), NOW
    )
    assert insufficient[0]["recommendation_details"]["category"] == "Further monitoring"
    assert "predictive conclusion" in insufficient[0]["recommendation_details"]["limitation"]


def test_missing_data_generates_verification_without_health_claim():
    records = intelligence_recommendations(
        bundle(findings=[{
            "rule_id": "data_quality.engine_temperature.missing",
            "parameter": "engine_temperature",
            "status": "NOT_ASSESSED",
            "condition": "data_quality",
            "explanation": "No value received.",
        }]),
        NOW,
    )
    details = records[0]["recommendation_details"]
    assert details["category"] == "Sensor data verification"
    assert details["decision"] == "OPERATOR REVIEW"


def test_all_scenario_contexts_and_synthetic_provenance_are_retained():
    scenarios = ("urban", "volcanic", "desert", "forest", "snow_mountain")
    for scenario in scenarios:
        record = intelligence_recommendations(bundle(scenario=scenario), NOW)[0]
        assert record["scenario"] == scenario
        assert record["recommendation_details"]["provenance"]["synthetic"] is True


def test_existing_operator_workflow_persists_and_rejects_duplicate_decision(tmp_path):
    service = TwinService(str(tmp_path / "phase6.sqlite3"))
    try:
        bridge = {
            "intelligence": bundle(findings=[finding("WARNING")]),
            "mode": "LIVE_LAPTOP1",
            "status": "disconnected",
            "latest_frame": None,
            "last_received_at": None,
            "last_error": "configuration_missing",
        }
        result = service.scenario_recommendations(bridge)
        record = next(
            item for item in result["recommendations"]
            if item["source"] == "SKYNEX_PHASE6_TEST"
        )
        assert record["status"] == "pending"
        approved = service.decide_recommendation(
            record["recommendation_id"], "approved", "Reviewed evidence."
        )
        assert approved["status"] == "approved"
        assert approved["operator_comment"] == "Reviewed evidence."
        assert any(
            item["recommendation_id"] == record["recommendation_id"]
            and item["status"] == "approved"
            for item in service.decision_history()
        )
        try:
            service.decide_recommendation(
                record["recommendation_id"], "rejected", "Duplicate."
            )
        except ValueError as error:
            assert "already been decided" in str(error)
        else:
            raise AssertionError("duplicate decision was accepted")
    finally:
        service.close()


def test_integration_has_no_control_action():
    details = intelligence_recommendations(bundle(findings=[finding("CRITICAL")]), NOW)[0]["recommendation_details"]
    assert "control" not in details["recommended_action"].lower()
    assert "execute" not in details["recommended_action"].lower()
