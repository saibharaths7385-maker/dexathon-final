"""Thread-safe single-engine service with durable SQLite checkpoints and history."""
import copy
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

from .model import EngineState, advance, assess, damage_rate, clamp
from .schemas import Controls, Telemetry, WhatIf
from .decision_support import INTELLIGENCE_RULESET, RULESET, evaluate, intelligence_recommendations
from .storage import connect_database


def utcnow():
    return datetime.now(timezone.utc)


class TwinService:
    def __init__(
        self,
        database: str,
        *,
        encryption_required: bool | None = None,
        database_key: str | None = None,
    ):
        self.lock = threading.RLock()
        if encryption_required is None:
            encryption_required = os.getenv(
                "TWIN_DATABASE_ENCRYPTION_REQUIRED", "true"
            ).strip().lower() in {"1", "true", "yes", "on"}
        self.db = connect_database(
            database,
            key=database_key or os.getenv("TWIN_DATABASE_KEY"),
            encryption_required=encryption_required,
        )
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS checkpoint (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS history (sequence INTEGER PRIMARY KEY, payload TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS missions (mission_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, updated_at TEXT NOT NULL, payload TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS fault_history (sequence INTEGER, timestamp TEXT, mission_id TEXT, payload TEXT NOT NULL, PRIMARY KEY(sequence, payload))")
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS operator_decisions (
                recommendation_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                aircraft_id TEXT NOT NULL,
                mission_id TEXT NOT NULL,
                scenario TEXT NOT NULL,
                recommendation_details TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')),
                operator_comment TEXT,
                created_at TEXT NOT NULL,
                decision_at TEXT
            )"""
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS operator_decisions_status_created "
            "ON operator_decisions(status, created_at DESC)"
        )
        self.db.commit()
        self.state = EngineState()
        self.controls = Controls()
        self.sequence = 0
        self.observed_at = None
        self.sample_source = "simulation"
        saved = self.db.execute("SELECT payload FROM checkpoint WHERE id=1").fetchone()
        if saved:
            data = json.loads(saved[0])
            self.state = EngineState(**data["state"])
            self.controls = Controls.model_validate(data["controls"])
            self.sequence = data["sequence"]
            self.observed_at = datetime.fromisoformat(data["observed_at"]) if data["observed_at"] else None
            self.sample_source = data["sample_source"]
        self.last_tick = monotonic()

    def snapshot(self):
        with self.lock:
            result = assess(self.state, self.controls)
            age = max(0, (utcnow() - self.observed_at).total_seconds()) if self.observed_at else None
            waiting = self.controls.source != self.sample_source or self.observed_at is None
            status = "waiting" if waiting else "paused" if self.controls.source == "simulation" and not self.controls.running else "stale" if age > 5 else "live"
            if status != "live":
                result["explainability"]["confidence_percent"] = 0
            return {**result, "engine_id": "VAYU-01", "sequence": self.sequence,
                    "timestamp": self.observed_at.isoformat() if self.observed_at else None,
                    "server_time": utcnow().isoformat(), "source": self.sample_source,
                    "controls": self.controls.model_dump(),
                    "quality": {"status": status, "age_seconds": round(age, 1) if age is not None else None,
                                "samples": self.state.samples, "sample_interval_seconds": 1},
                    "disclaimer": "Synthetic research demonstrator. Model-derived estimates require engine-specific calibration; not flight clearance."}

    def _save(self, record=True):
        with self.lock:
            previous_sequence = self.sequence
            try:
                self.db.execute("BEGIN IMMEDIATE")
                saved = self.db.execute(
                    "SELECT payload FROM checkpoint WHERE id=1"
                ).fetchone()
                checkpoint_sequence = (
                    json.loads(saved[0]).get("sequence", 0) if saved else 0
                )
                history_sequence = self.db.execute(
                    "SELECT COALESCE(MAX(sequence), 0) FROM history"
                ).fetchone()[0]
                self.sequence = max(
                    self.sequence, checkpoint_sequence, history_sequence
                ) + 1
                payload = {
                    "state": {
                        "sensors": self.state.sensors,
                        "wear": self.state.wear,
                        "elapsed_seconds": self.state.elapsed_seconds,
                        "samples": self.state.samples,
                        "fault_elapsed_seconds": self.state.fault_elapsed_seconds,
                    },
                    "controls": self.controls.model_dump(),
                    "sequence": self.sequence,
                    "observed_at": (
                        self.observed_at.isoformat() if self.observed_at else None
                    ),
                    "sample_source": self.sample_source,
                }
                self.db.execute(
                    "INSERT OR REPLACE INTO checkpoint VALUES (1, ?)",
                    (json.dumps(payload),),
                )
                if record:
                    snapshot = self.snapshot()
                    row = {
                        key: snapshot[key]
                        for key in (
                            "timestamp",
                            "sequence",
                            "sensors",
                            "expected",
                            "health_index",
                            "source",
                        )
                    }
                    row["reliability_percent"] = snapshot["mission"][
                        "reliability_percent"
                    ]
                    row["rul_hours"] = snapshot["rul"]["hours"]
                    self.db.execute(
                        "INSERT INTO history VALUES (?, ?)",
                        (self.sequence, json.dumps(row)),
                    )
                    self.db.execute(
                        "DELETE FROM history WHERE sequence NOT IN "
                        "(SELECT sequence FROM history ORDER BY sequence DESC LIMIT 3600)"
                    )
                    mission_id = self.controls.mission.mission_id
                    for fault in snapshot["maintenance"]:
                        if fault["priority"] != "routine":
                            self.db.execute(
                                "INSERT OR IGNORE INTO fault_history VALUES (?, ?, ?, ?)",
                                (
                                    self.sequence,
                                    snapshot["timestamp"],
                                    mission_id,
                                    json.dumps(fault),
                                ),
                            )
                    self.db.execute(
                        "INSERT OR IGNORE INTO missions VALUES (?, ?, ?, ?)",
                        (
                            mission_id,
                            snapshot["timestamp"] or utcnow().isoformat(),
                            utcnow().isoformat(),
                            json.dumps(snapshot),
                        ),
                    )
                    self.db.execute(
                        "UPDATE missions SET updated_at=?, payload=? WHERE mission_id=?",
                        (utcnow().isoformat(), json.dumps(snapshot), mission_id),
                    )
                self.db.commit()
            except Exception:
                self.db.rollback()
                self.sequence = previous_sequence
                raise

    def tick(self):
        with self.lock:
            now = monotonic()
            dt = min(5, max(0, now - self.last_tick))
            self.last_tick = now
            if self.controls.source == "simulation" and self.controls.running:
                advance(self.state, self.controls, dt)
                self.observed_at = utcnow()
                self.sample_source = "simulation"
                self._save()

    def configure(self, controls: Controls):
        with self.lock:
            if controls.scenario != self.controls.scenario:
                self.state.fault_elapsed_seconds = 0.0
            self.controls = controls.model_copy(deep=True)
            mission_id, now = self.controls.mission.mission_id, utcnow().isoformat()
            with self.db:
                self.db.execute("INSERT OR IGNORE INTO missions VALUES (?, ?, ?, ?)", (mission_id, now, now, json.dumps(self.snapshot())))
            self.last_tick = monotonic()
            self._save(record=False)
            return self.snapshot()

    def reset_demo(self, scenario: str):
        """Reset only the synthetic simulator to its known healthy baseline."""
        with self.lock:
            if self.controls.source != "simulation":
                raise ValueError("Select the built-in simulation source before starting Judge Demo Mode.")
            controls = self.controls.model_copy(deep=True)
            controls.scenario = scenario
            controls.running = True
            self.state = EngineState()
            self.controls = controls
            self.observed_at = utcnow()
            self.sample_source = "simulation"
            self.last_tick = monotonic()
            self._save()
            return self.snapshot()

    def ingest(self, telemetry: Telemetry):
        with self.lock:
            if self.controls.source != "telemetry":
                raise ValueError("Select telemetry source before ingesting external samples.")
            age = (utcnow() - telemetry.timestamp).total_seconds()
            if age < -2 or age > 10:
                raise ValueError("Telemetry timestamp must be within the last 10 seconds and at most 2 seconds in the future.")
            previous = self.observed_at if self.sample_source == "telemetry" else None
            if previous and telemetry.timestamp <= previous:
                raise ValueError("Telemetry timestamps must be strictly increasing.")
            dt = min(10, (telemetry.timestamp - previous).total_seconds()) if previous else 0
            self.state.sensors = telemetry.sensors.model_dump()
            self.state.wear = clamp(self.state.wear + damage_rate(self.state.sensors, self.controls) * dt / 3600)
            self.state.elapsed_seconds += dt
            self.state.samples += 1
            self.observed_at = telemetry.timestamp
            self.sample_source = "telemetry"
            self._save()
            return self.snapshot()

    def history(self, limit=180):
        with self.lock:
            rows = self.db.execute("SELECT payload FROM history ORDER BY sequence DESC LIMIT ?", (limit,)).fetchall()
            return [json.loads(row[0]) for row in reversed(rows)]

    def missions(self, limit=24):
        with self.lock:
            rows = self.db.execute("SELECT mission_id, started_at, updated_at, payload FROM missions ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
            return [{"mission_id": row[0], "started_at": row[1], "updated_at": row[2], "snapshot": json.loads(row[3])} for row in rows]

    def fault_history(self, limit=180):
        with self.lock:
            rows = self.db.execute("SELECT sequence, timestamp, mission_id, payload FROM fault_history ORDER BY sequence DESC LIMIT ?", (limit,)).fetchall()
            return [{"sequence": row[0], "timestamp": row[1], "mission_id": row[2], "fault": json.loads(row[3])} for row in rows]

    @staticmethod
    def _decision_from_row(row):
        return {
            "recommendation_id": row[0],
            "source": row[1],
            "aircraft_id": row[2],
            "mission_id": row[3],
            "scenario": row[4],
            "recommendation_details": json.loads(row[5]),
            "status": row[6],
            "operator_comment": row[7],
            "created_at": row[8],
            "decision_at": row[9],
        }

    def record_current_recommendation(self, snapshot):
        maintenance = snapshot["maintenance"]
        primary = next(
            (item for item in maintenance if item["priority"] != "routine"),
            maintenance[0],
        )
        feature_by_key = {
            item["key"]: item for item in snapshot["explainability"]["features"]
        }
        evidence = [
            {
                "key": key,
                "label": feature_by_key[key]["label"],
                "value": feature_by_key[key]["value"],
                "expected": feature_by_key[key]["expected"],
                "unit": feature_by_key[key]["unit"],
                "status": feature_by_key[key]["status"],
            }
            for key in primary["features"]
            if key in feature_by_key
        ]
        twin_source = snapshot["source"]
        source = (
            "SKYNEX_V2_EXTERNAL_ENGINE_TELEMETRY"
            if twin_source == "telemetry"
            else "SKYNEX_V2_BUILT_IN_SIMULATION"
        )
        details = {
            "decision": snapshot["mission"]["decision"],
            "failure_mode": primary["failure_mode"],
            "severity": primary["priority"],
            "reason": primary["reason"],
            "recommended_action": primary["recommended_action"],
            "evidence": evidence,
        }
        identity = {
            "source": source,
            "aircraft_id": snapshot["engine_id"],
            "mission_id": snapshot["controls"]["mission"]["mission_id"],
            "scenario": snapshot["controls"]["scenario"],
            "decision": details["decision"],
            "failure_mode": details["failure_mode"],
            "severity": details["severity"],
            "recommended_action": details["recommended_action"],
        }
        return self._record_recommendation(identity, details)

    def _record_recommendation(self, identity, details):
        """Reuse the original immutable evidence and operator-decision workflow."""
        recommendation_id = hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode("utf-8")
        ).hexdigest()[:32]
        created_at = utcnow().isoformat()

        with self.lock:
            self.db.execute(
                """INSERT OR IGNORE INTO operator_decisions
                (recommendation_id, source, aircraft_id, mission_id, scenario,
                 recommendation_details, status, operator_comment, created_at, decision_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL, ?, NULL)""",
                (
                    recommendation_id,
                    identity["source"],
                    identity["aircraft_id"],
                    identity["mission_id"],
                    identity["scenario"],
                    json.dumps(details),
                    created_at,
                ),
            )
            self.db.commit()
            row = self.db.execute(
                """SELECT recommendation_id, source, aircraft_id, mission_id, scenario,
                recommendation_details, status, operator_comment, created_at, decision_at
                FROM operator_decisions WHERE recommendation_id=?""",
                (recommendation_id,),
            ).fetchone()
            return self._decision_from_row(row)

    def scenario_recommendations(self, bridge):
        with self.lock:
            now = utcnow()
            candidates = evaluate(self.snapshot(), bridge, now)
            records = []
            for candidate in candidates:
                details = candidate["recommendation_details"]
                identity = {key: candidate[key] for key in ("source", "aircraft_id", "mission_id", "scenario")}
                identity.update({key: details.get(key) for key in (
                    "rule_id", "ruleset_version", "severity", "recommended_action", "phase", "quality", "fault_signature")})
                if details.get("algorithm_version") == "phase6-intelligence-advisory-1.0":
                    identity["evidence_fingerprint"] = details.get("evidence_fingerprint")
                if details.get("replay_session_id"):
                    identity["replay_session_id"] = details["replay_session_id"]
                record = self._record_recommendation(identity, details)
                # Never replace the evidence that was approved. Current evidence is separate.
                records.append({**record, "current_details": details})
            return {"ruleset_version": RULESET, "evaluated_at": now.isoformat(),
                    "source_mode": bridge.get("mode", "LIVE_LAPTOP1"),
                    "replay_session_id": bridge.get("replay", {}).get("session_id"),
                    "advisory_only": True, "recommendations": records}

    def intelligence_recommendations(self, bundle):
        """Persist Phase 2–5 advisory candidates through the existing workflow."""
        with self.lock:
            now = utcnow()
            records = []
            for candidate in intelligence_recommendations(bundle, now):
                details = candidate["recommendation_details"]
                identity = {key: candidate[key] for key in (
                    "source", "aircraft_id", "mission_id", "scenario"
                )}
                identity.update({
                    key: details.get(key) for key in (
                        "rule_id", "algorithm_version", "severity",
                        "recommended_action", "evidence_fingerprint"
                    )
                })
                record = self._record_recommendation(identity, details)
                records.append({**record, "current_details": details})
            return {
                "ruleset_version": INTELLIGENCE_RULESET,
                "evaluated_at": now.isoformat(),
                "advisory_only": True,
                "recommendations": records,
            }

    def pending_recommendations(self, limit=100):
        with self.lock:
            rows = self.db.execute(
                """SELECT recommendation_id, source, aircraft_id, mission_id, scenario,
                recommendation_details, status, operator_comment, created_at, decision_at
                FROM operator_decisions WHERE status='pending'
                ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [self._decision_from_row(row) for row in rows]

    def decision_history(self, limit=200):
        with self.lock:
            rows = self.db.execute(
                """SELECT recommendation_id, source, aircraft_id, mission_id, scenario,
                recommendation_details, status, operator_comment, created_at, decision_at
                FROM operator_decisions
                ORDER BY COALESCE(decision_at, created_at) DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [self._decision_from_row(row) for row in rows]

    def decide_recommendation(self, recommendation_id, status, operator_comment):
        decision_at = utcnow().isoformat()
        with self.lock:
            cursor = self.db.execute(
                """UPDATE operator_decisions
                SET status=?, operator_comment=?, decision_at=?
                WHERE recommendation_id=? AND status='pending'""",
                (status, operator_comment, decision_at, recommendation_id),
            )
            self.db.commit()
            if cursor.rowcount == 0:
                exists = self.db.execute(
                    "SELECT status FROM operator_decisions WHERE recommendation_id=?",
                    (recommendation_id,),
                ).fetchone()
                if exists is None:
                    raise LookupError("Recommendation not found.")
                raise ValueError("Recommendation has already been decided.")

            row = self.db.execute(
                """SELECT recommendation_id, source, aircraft_id, mission_id, scenario,
                recommendation_details, status, operator_comment, created_at, decision_at
                FROM operator_decisions WHERE recommendation_id=?""",
                (recommendation_id,),
            ).fetchone()
            return self._decision_from_row(row)

    def fleet_snapshot(self):
        """Concurrent fleet overview derived from the live lead asset and stored condition model."""
        lead = self.snapshot()
        offsets = [("VAYU-01", "LEAD", 0, 0.0, "ACTIVE"), ("VAYU-02", "NORTH", -4, .03, "ACTIVE"), ("VAYU-03", "EAST", -12, .12, "MONITOR"), ("VAYU-04", "SOUTH", 3, -.02, "READY"), ("VAYU-05", "WEST", -22, .22, "INSPECT")]
        positions = {"LEAD": (50, 50), "NORTH": (50, 22), "EAST": (77, 50), "SOUTH": (50, 78), "WEST": (23, 50)}
        assets = []
        for engine_id, sector, health_offset, wear_offset, status in offsets:
            health = round(clamp((lead["health_index"] + health_offset) / 100) * 100, 1)
            reliability = round(clamp((lead["mission"]["reliability_percent"] + health_offset * .8) / 100) * 100, 1)
            x, y = positions[sector]
            assets.append({"engine_id": engine_id, "callsign": engine_id.replace("VAYU", "MALE"), "sector": sector, "health_index": health,
                "reliability_percent": reliability, "rul_hours": round(max(0, lead["rul"]["hours"] * max(.15, 1 - wear_offset)), 1), "risk_percent": round(100 - reliability, 1),
                "readiness": status, "coordinates": {"x": x, "y": y}})
        ready = [asset for asset in assets if asset["readiness"] in ("ACTIVE", "READY")]
        return {"generated_at": utcnow().isoformat(), "assets": assets, "summary": {"asset_count": len(assets), "fleet_health": round(sum(a["health_index"] for a in assets) / len(assets), 1),
            "fleet_readiness_score": round(sum(a["reliability_percent"] for a in assets) / len(assets), 1), "mission_available": len(ready), "mission_availability_percent": round(len(ready) / len(assets) * 100, 1), "high_risk_assets": sum(a["risk_percent"] >= 20 for a in assets)}}

    def what_if(self, request: WhatIf):
        with self.lock:
            base_state, alternate = copy.deepcopy(self.state), copy.deepcopy(self.state)
            original, changed = self.controls.model_copy(deep=True), self.controls.model_copy(deep=True)
            sequence = self.sequence
            quality = self.snapshot()["quality"]
        changed.rpm_target = clamp(original.rpm_target + request.rpm_adjustment, 2000, 5800)
        changed.ambient_temperature = clamp(original.ambient_temperature + request.temperature_variation, -20, 55)
        changed.fuel_flow_multiplier = clamp(original.fuel_flow_multiplier * (1 + request.fuel_flow_variation / 100), .7, 1.3)
        trajectory = []
        # Both branches evolve for the same horizon; no live state is modified.
        steps = int(request.horizon_minutes * 6)
        for index in range(steps + 1):
            if index:
                advance(base_state, original, 10, noise=False)
                advance(alternate, changed, 10, noise=False)
            if index % max(1, steps // 30) == 0 or index == steps:
                baseline, candidate = assess(base_state, original), assess(alternate, changed)
                trajectory.append({"minutes": round(index / 6, 2), "baseline_reliability": baseline["mission"]["reliability_percent"],
                                   "candidate_reliability": candidate["mission"]["reliability_percent"],
                                   "baseline_rul": baseline["rul"]["hours"], "candidate_rul": candidate["rul"]["hours"]})
        return {"baseline_sequence": sequence, "baseline_quality": quality, "request": request.model_dump(),
                "effective_controls": changed.model_dump(), "baseline": baseline, "candidate": candidate,
                "delta": {"reliability_points": round(candidate["mission"]["reliability_percent"] - baseline["mission"]["reliability_percent"], 2),
                          "rul_hours": round(candidate["rul"]["hours"] - baseline["rul"]["hours"], 1),
                          "health_points": round(candidate["health_index"] - baseline["health_index"], 1)},
                "trajectory": trajectory,
                "assumption": "Same-horizon reduced-order forecast, holding selected fault scenario and mission conditions constant. External telemetry faults are not identified automatically for forecast propagation."}

    def close(self):
        with self.lock:
            self.db.close()
