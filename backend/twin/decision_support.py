"""Deterministic advisory rules. No aircraft commands or learned models.

Engineering constants come only from the existing synthetic V2 model. Protocol 1
has no verified engineering limits; its payload is evidence, never a twin input.
See docs/PHASE3_DECISION_SUPPORT.md for scope and rule provenance.
"""
import hashlib
import json
from datetime import datetime

from .laptop1 import FRESHNESS_SECONDS
from .model import EngineState, SIGNALS, assess
from .schemas import Controls

RULESET = "scenario-advisory-3.0.0"
INTELLIGENCE_RULESET = "phase6-intelligence-advisory-1.0"
LAPTOP_SOURCE = "LAPTOP1_PROTOCOL1"

# Documentation of predicates already implemented by model.assess, not new limits.
RULE_BASIS = {
    "engine_degradation": "Injected engine_degradation; ramp severity > 0.18.",
    "sensor_bias": "Injected sensor_bias; ramp severity > 0.12.",
    "fuel_leak": "Injected fuel_leak; ramp severity > 0.12.",
    "compressor_fouling": "Injected compressor_fouling; ramp severity > 0.12.",
    "lubrication_pressure_loss": "Oil pressure < 2.5 bar.",
    "thermal_overload": "CHT > 220 °C OR oil temperature > 120 °C.",
    "rotating_assembly_anomaly": "Vibration > 5 mm/s RMS.",
    "fuel_delivery_anomaly": "Fuel flow < 0.8 × operating-point expected fuel flow (L/h).",
    "power_or_combustion_deviation": "Absolute RPM residual > 700 rpm OR EGT > 820 °C.",
    "sensor_envelope_excursion": "Uncovered channel outside model.SIGNALS nominal envelope.",
    "routine_condition_inspection": "No existing V2 maintenance predicate is active.",
}


def evidence(key, value, unit="", **extra):
    return {"key": key, "label": key, "value": value, "unit": unit, **extra}


def advisory(context, rule_id, category, severity, action, reason, items, now, **extra):
    return {
        **context,
        "recommendation_details": {
            "rule_id": rule_id, "ruleset_version": RULESET, "advisory_only": True,
            "category": category, "failure_mode": category, "severity": severity,
            "recommended_action": action, "reason": reason, "evidence": items,
            "timestamp": now.isoformat(), "decision": "OPERATOR REVIEW",
            **extra,
        },
    }


def intelligence_recommendations(bundle, now):
    """Translate Phase 2–5 evidence into advisory records.

    The bundle is intentionally supplied by the caller so this adapter does
    not reinterpret raw telemetry or invent thresholds. It only creates
    traceable recommendations for evidence already assessed upstream.
    """
    engineering = bundle.get("engineering_assessment") or {}
    trends = bundle.get("trend_assessments") or []
    health = bundle.get("health_assessment") or {}
    context = {
        "source": bundle.get("source", "SKYNEX_PHASE6_INTELLIGENCE"),
        "aircraft_id": bundle.get("aircraft_id", engineering.get("aircraft_id", "unavailable")),
        "mission_id": bundle.get("mission_id", engineering.get("mission_id", "unavailable")),
        "scenario": bundle.get("scenario_id", engineering.get("scenario_id", "unavailable")),
    }
    recommendations = []
    findings = engineering.get("findings") if isinstance(engineering.get("findings"), list) else []
    critical = [item for item in findings if item.get("status") == "CRITICAL"]
    warnings = [item for item in findings if item.get("status") == "WARNING"]
    missing = [
        item for item in findings
        if item.get("status") == "NOT_ASSESSED"
        and item.get("condition") == "data_quality"
    ]

    def make(rule_id, category, severity, title, action, reason, evidence, **extra):
        evidence_fingerprint = hashlib.sha256(
            json.dumps(evidence, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]
        return advisory(
            context,
            rule_id,
            category,
            severity,
            action,
            reason,
            evidence,
            now,
            title=title,
            algorithm_version=INTELLIGENCE_RULESET,
            provenance=health.get("provenance") or engineering.get("raw_telemetry", {}),
            health_status=health.get("status"),
            evidence_fingerprint=evidence_fingerprint,
            **extra,
        )

    if critical:
        recommendations.append(make(
            "phase6.engine.critical",
            "Engine parameter inspection",
            "critical",
            "Review critical engineering evidence",
            "Have an appropriately qualified operator review the critical parameter evidence and approved procedure.",
            "A configured engineering assessment contains critical findings; this is an advisory review, not a confirmed fault.",
            critical,
            engineering_findings=critical,
            trend_evidence=trends,
        ))
    elif warnings:
        recommendations.append(make(
            "phase6.engine.warning",
            "Engine parameter inspection",
            "warning",
            "Review warning-level engineering evidence",
            "Review the affected parameter and applicable approved inspection procedure.",
            "A configured engineering assessment contains warning findings supported by received telemetry.",
            warnings,
            engineering_findings=warnings,
            trend_evidence=trends,
        ))

    high_trends = [item for item in trends if item.get("risk_category") == "HIGH"]
    moderate_trends = [item for item in trends if item.get("risk_category") == "MODERATE"]
    if high_trends:
        recommendations.append(make(
            "phase6.trend.high",
            "Historical trend inspection",
            "warning",
            "Review persistent historical trend evidence",
            "Review the contributing parameter trend and continue qualified monitoring.",
            "Historical evidence indicates an experimental high trend band; it is not a failure prediction or approved operating limit.",
            high_trends,
            trend_evidence=high_trends,
            limitation="Experimental trend indicator; no failure probability or RUL.",
        ))
    elif moderate_trends:
        recommendations.append(make(
            "phase6.trend.moderate",
            "Historical trend inspection",
            "warning",
            "Monitor moderate historical trend evidence",
            "Continue monitoring the contributing parameter and obtain additional valid history.",
            "Historical evidence indicates an experimental moderate trend band; evidence is insufficient for a confirmed fault.",
            moderate_trends,
            trend_evidence=moderate_trends,
            limitation="Experimental trend indicator; no failure probability or RUL.",
        ))

    if missing or not engineering.get("data_quality"):
        recommendations.append(make(
            "phase6.data_quality",
            "Sensor data verification",
            "warning",
            "Verify telemetry data quality",
            "Verify the affected sensors, timestamps, and telemetry source before condition interpretation.",
            "Missing or invalid telemetry prevents a reliable engineering assessment; missing data is not treated as healthy.",
            missing or [{"data_quality": engineering.get("data_quality")}],
            data_quality=engineering.get("data_quality"),
        ))

    insufficient = [
        item for item in trends
        if item.get("risk_category") == "INSUFFICIENT_DATA"
    ]
    if insufficient and not (critical or warnings or high_trends or moderate_trends):
        recommendations.append(make(
            "phase6.monitoring.insufficient_history",
            "Further monitoring",
            "info",
            "Collect additional valid telemetry history",
            "Continue monitoring and collect sufficient timestamp-ordered observations.",
            "Historical evidence is insufficient for a supported trend-risk indicator; no predictive fault claim is made.",
            insufficient,
            trend_evidence=insufficient,
            limitation="Insufficient history; no predictive conclusion.",
        ))

    if not recommendations:
        recommendations.append(make(
            "phase6.monitoring",
            "Further monitoring",
            "info",
            "Continue evidence-based monitoring",
            "Continue monitoring and review new evidence when available.",
            "No warning or critical finding was supplied; this does not establish that the engine is healthy.",
            [{"health_status": health.get("status"), "data_quality": engineering.get("data_quality")}],
            limitation="No confirmed fault, probability, or RUL is produced.",
        ))
    return recommendations


def age_seconds(value, now):
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.utcoffset() is None:
            return None
        return (now - stamp).total_seconds()
    except (ValueError, TypeError, AttributeError):
        return None


def twin_recommendations(snapshot, now):
    source = snapshot["source"]
    context = {
        "source": "SKYNEX_V2_EXTERNAL_ENGINE_TELEMETRY" if source == "telemetry" else "SKYNEX_V2_BUILT_IN_SIMULATION",
        "aircraft_id": snapshot["engine_id"],
        "mission_id": snapshot["controls"]["mission"]["mission_id"],
        # External engine samples do not carry a scenario or aircraft ID.
        "scenario": snapshot["controls"]["scenario"] if source == "simulation" else "unreported",
    }
    quality = snapshot["quality"]["status"]
    age = age_seconds(snapshot.get("timestamp"), now)
    if quality != "live" or age is None or age > 5 or age < -2:
        return [advisory(context, "twin.data_quality", "Telemetry quality", "warning",
            "Restore a fresh engine sample before reviewing condition advice.",
            "V2 data is waiting, paused, stale or has an invalid timestamp; condition rules are withheld.",
            [evidence("quality.status", quality), evidence("sample_age", age, "s")], now,
            quality=quality, identity_basis="V2 engine ID; aircraft registration not supplied by this schema.",
            sample_timestamp=snapshot.get("timestamp"), rule_basis="V2 service: live quality and sample age ≤ 5 s; future tolerance 2 s.")]

    result = snapshot
    if source == "telemetry":
        # A selected simulation fault must never diagnose an external sample.
        controls = Controls.model_validate(snapshot["controls"])
        controls.scenario = "nominal"
        result = assess(EngineState(sensors=snapshot["sensors"],
            wear=snapshot["wear_percent"] / 100, samples=snapshot["quality"]["samples"]), controls)
    features = {item["key"]: item for item in result["explainability"]["features"]}
    recommendations = []
    for fault in result["maintenance"]:
        keys = fault["features"] or list(features)
        items = [{**features[key], "residual_tolerance": SIGNALS[key][6],
            # Normalize the existing model's mojibake Celsius label, not its values.
            "unit": "°C" if key in {"egt", "cht", "oil_temperature"} else features[key]["unit"]}
            for key in keys]
        if source == "simulation" and fault["id"] in {"engine_degradation", "sensor_bias", "fuel_leak", "compressor_fouling"}:
            items.append(evidence("fault_progress.severity_percent", result["fault_progress"]["severity_percent"], "%"))
        recommendations.append(advisory(context, "v2." + fault["id"], fault["failure_mode"], fault["priority"],
            fault["recommended_action"], fault["reason"], items, now,
            decision=result["mission"]["decision"], sample_timestamp=snapshot["timestamp"],
            identity_basis="V2 engine ID; aircraft registration not supplied by this schema.",
            rule_basis=RULE_BASIS[fault["id"]],
            limitation="Existing synthetic V2 demonstration envelopes; not aircraft engineering limits.",
            rule_source="backend/twin/model.py:assess"))
    if result["mission"]["decision"] != "WITHIN DEMO ENVELOPE":
        decision = result["mission"]["decision"]
        recommendations.append(advisory(context, "v2.mission_review", "Model mission risk",
            "critical" if decision == "HOLD / INSPECT" else "high",
            "Review the model findings and mission assumptions with the operator before proceeding.",
            "The existing V2 demonstration mission gate requests review; this is not flight clearance.",
            [evidence("health_index", result["health_index"], "/100"),
             evidence("mission.reliability_percent", result["mission"]["reliability_percent"], "%"),
             evidence("maintenance.priorities", [f["priority"] for f in result["maintenance"]])], now,
            decision=decision, sample_timestamp=snapshot["timestamp"],
            identity_basis="V2 engine ID; aircraft registration not supplied by this schema.",
            rule_basis="HOLD: critical maintenance OR reliability < 80% OR health < 55; REVIEW: reliability < 95% OR high maintenance.",
            rule_source="backend/twin/model.py:assess",
            limitation="Model-derived demonstration scores, not validated probabilities."))
    return recommendations


def protocol1_recommendations(bridge, now):
    """Common input boundary for live and offline Protocol 1 assessment."""
    offline = bridge.get("mode") == "OFFLINE_REPLAY"
    label = "Offline replay" if offline else "Laptop 1"
    frame = bridge.get("latest_frame") or {}
    context = {"source": "OFFLINE_REPLAY" if offline else LAPTOP_SOURCE,
        "aircraft_id": frame.get("aircraft_id", "unavailable"),
        "mission_id": frame.get("mission_id", "unavailable"),
        "scenario": frame.get("scenario", "unavailable")}
    sample_age = age_seconds(frame.get("timestamp"), now)
    receipt_age = age_seconds(bridge.get("last_received_at"), now)
    problem = None
    if not frame:
        problem = "missing"
    elif bridge.get("status") != "connected":
        problem = bridge.get("status", "unavailable")
    elif bridge.get("last_error"):
        problem = bridge["last_error"]
    elif sample_age is None or receipt_age is None:
        problem = "invalid_timestamp"
    elif sample_age < -FRESHNESS_SECONDS or receipt_age < 0:
        problem = "clock_mismatch"
    elif max(sample_age, receipt_age) > FRESHNESS_SECONDS:
        problem = "stale"
    elif not all(isinstance(frame.get(key), dict) for key in ("flight", "propulsion", "environment", "mission")) or not isinstance(frame.get("faults"), (list, dict)):
        problem = "unsupported_payload"
    items = [evidence("bridge.status", bridge.get("status")),
        evidence("bridge.last_error", bridge.get("last_error")),
        evidence("sample_age", sample_age, "s"), evidence("receipt_age", receipt_age, "s"),
        evidence("seq", frame.get("seq"))]
    if problem:
        return [advisory(context, "protocol1.data_quality", "Telemetry quality", "warning",
            "Verify replay controls, fixture validity and replay clock before reviewing synthetic condition."
            if offline else "Verify the simulator connection, clock and Protocol 1 payload before reviewing aircraft condition.",
            f"{label} telemetry is {problem}; source-fault and condition advice is withheld.", items, now,
            sample_timestamp=frame.get("timestamp"), phase=frame.get("phase"),
            rule_basis="Existing bridge freshness window: 2 s. Apply to receipt and source timestamp; future tolerance 2 s.",
            quality=problem)]
    faults = frame["faults"]
    return [advisory(context,
        "protocol1.source_faults" if faults else "protocol1.no_reported_faults",
        "Source-reported fault review" if faults else "Source monitoring",
        "warning" if faults else "info",
        "Review the reported faults against the simulator's scenario definition and approved operating procedures."
        if faults else "Continue monitoring; obtain verified scenario limits before making a condition decision.",
        f"{label} reports fault entries; fault semantics and severity have not been independently verified."
        if faults else "The fresh frame contains no fault entries. This does not establish that the aircraft is healthy.",
        items + [evidence("faults", faults), evidence("phase", frame["phase"])], now,
        phase=frame["phase"], sample_timestamp=frame["timestamp"],
        fault_signature=hashlib.sha256(json.dumps(faults, sort_keys=True).encode()).hexdigest(),
        rule_basis="Presence or absence of raw Protocol 1 fault entries; no numerical aircraft thresholds.",
        limitation="Scenario-specific limits, fault semantics and engineering units remain unverified. No propulsion-to-V2 mapping.")]


# Keep the Phase 3 import contract for existing callers/tests.
laptop1_recommendations = protocol1_recommendations


def evaluate(twin, bridge, now):
    if bridge.get("mode") == "OFFLINE_REPLAY":
        replay = bridge["replay"]
        replay_now = datetime.fromisoformat(replay["virtual_time"])
        recommendations = protocol1_recommendations(bridge, replay_now)
        for item in recommendations:
            item["recommendation_details"].update(
                timestamp=now.isoformat(), source_mode="OFFLINE_REPLAY",
                replay_session_id=replay["session_id"], replay_scenario=replay["scenario"],
                replay_time=replay["virtual_time"], synthetic=replay["synthetic"],
                fixture_id=replay["fixture_id"], fixture_sha256=replay["fixture_sha256"],
                provenance=replay["provenance"], replay_state=replay["state"],
            )
    else:
        recommendations = twin_recommendations(twin, now) + protocol1_recommendations(bridge, now)
    if isinstance(bridge.get("intelligence"), dict):
        recommendations.extend(intelligence_recommendations(bridge["intelligence"], now))
    order = {"critical": 0, "high": 1, "warning": 2, "info": 3, "routine": 4}
    recommendations.sort(key=lambda item: (order[item["recommendation_details"]["severity"]], item["source"], item["recommendation_details"]["rule_id"]))
    return recommendations
