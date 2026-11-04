"""Validated, provenance-preserving telemetry preprocessing.

This module consumes frames returned by ``normalize_telemetry_frame``. It does
not apply engineering thresholds or infer health, faults, probabilities, or
remaining useful life.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

SUPPORTED_SCENARIOS = frozenset(
    {"urban", "volcanic", "desert", "forest", "snow_mountain"}
)


@dataclass(frozen=True)
class SensorLimits:
    """Configurable data-validity limits, not engineering operating limits."""

    rpm_min: float = 0.0
    voltage_min: float = 0.0
    current_min: float = 0.0
    fuel_percent_min: float = 0.0
    fuel_percent_max: float = 100.0


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def _sensor(
    section: dict[str, Any],
    key: str,
    *,
    unit: str,
    source: str,
    aliases: tuple[str, ...] = (),
    minimum: float | None = None,
    maximum: float | None = None,
) -> dict[str, Any]:
    present_key = next((candidate for candidate in (key, *aliases) if candidate in section), None)
    if present_key is None:
        return {"status": "missing", "value": None, "unit": unit, "source": source}
    value = section[present_key]
    if not _finite_number(value):
        return {"status": "invalid", "value": None, "unit": unit, "source": source}
    numeric = float(value)
    if (minimum is not None and numeric < minimum) or (
        maximum is not None and numeric > maximum
    ):
        return {"status": "invalid", "value": numeric, "unit": unit, "source": source}
    return {"status": "valid", "value": numeric, "unit": unit, "source": source}


def preprocess_normalized_frame(
    frame: dict[str, Any],
    *,
    limits: SensorLimits | None = None,
) -> dict[str, Any]:
    """Validate a normalized Protocol 1 frame without mutating it.

    Invalid sensor values make the individual sensor invalid while preserving
    the frame for quality reporting. Missing required frame metadata rejects
    the frame because identity and ordering cannot be established safely.
    """

    configured = limits or SensorLimits()
    raw = copy.deepcopy(frame)
    if not isinstance(frame, dict):
        return {
            "accepted": False,
            "raw_telemetry": raw,
            "errors": ["frame must be a mapping"],
        }

    errors: list[str] = []
    required = ("timestamp", "aircraft_id", "mission_id", "scenario")
    for field in required:
        if field not in frame or not isinstance(frame[field], str) or not frame[field].strip():
            errors.append(f"{field} is missing")
    parsed_timestamp = _timestamp(frame.get("timestamp"))
    if "timestamp" in frame and parsed_timestamp is None:
        errors.append("timestamp must be timezone-aware ISO 8601 text")

    propulsion = frame.get("propulsion")
    environment = frame.get("environment")
    if not isinstance(propulsion, dict):
        errors.append("propulsion must be a mapping")
        propulsion = {}
    if not isinstance(environment, dict):
        errors.append("environment must be a mapping")
        environment = {}

    normalization = frame.get("normalization")
    temperature_kind = normalization.get("temperature_kind") if isinstance(normalization, dict) else None
    rpm_kind = normalization.get("rpm_kind") if isinstance(normalization, dict) else None
    aircraft_id = frame.get("aircraft_id", "").upper()
    rpm_aliases = ("engine_rpm", "rpm") if aircraft_id != "RQ11B" else ("motor_rpm", "rpm")
    temperature_aliases = ("engine_temp_c", "temperature_c") if aircraft_id != "RQ11B" else ()
    sensors = {
        "rpm": _sensor(
            propulsion,
            "rpm",
            unit="rpm",
            source=f"propulsion.{rpm_kind}_rpm" if rpm_kind else "propulsion.rpm",
            aliases=rpm_aliases,
            minimum=configured.rpm_min,
        ),
        "engine_temperature": (
            _sensor(
                propulsion,
                "temperature_c",
                unit="°C",
                source="propulsion.engine_temp_c",
                aliases=temperature_aliases,
            )
            if temperature_kind == "engine"
            or (aircraft_id != "RQ11B" and any(key in propulsion for key in temperature_aliases))
            else {"status": "missing", "value": None, "unit": "°C", "source": None,
                  "note": "motor temperature is not engine temperature"}
        ),
        "battery_voltage": _sensor(
            propulsion,
            "battery_voltage",
            unit="V",
            source="propulsion.battery_voltage",
            aliases=("battery_voltage_v",),
            minimum=configured.voltage_min,
        ),
        "electrical_current": _sensor(
            propulsion,
            "current_a",
            unit="A",
            source="propulsion.current_a",
            minimum=configured.current_min,
        ),
        "fuel_percent": _sensor(
            propulsion,
            "fuel_percent",
            unit="%",
            source="propulsion.fuel_percent",
            aliases=("fuel_pct",),
            minimum=configured.fuel_percent_min,
            maximum=configured.fuel_percent_max,
        ),
    }

    environmental = {
        key: copy.deepcopy(value)
        for key, value in environment.items()
    }
    valid_count = sum(item["status"] == "valid" for item in sensors.values())
    quality = {
        "valid_sensor_count": valid_count,
        "sensor_count": len(sensors),
        "missing_sensors": [key for key, item in sensors.items() if item["status"] == "missing"],
        "invalid_sensors": [key for key, item in sensors.items() if item["status"] == "invalid"],
    }
    return {
        "accepted": not errors,
        "errors": errors,
        "raw_telemetry": raw,
        "timestamp": frame.get("timestamp"),
        "aircraft_id": frame.get("aircraft_id"),
        "mission_id": frame.get("mission_id"),
        "scenario_id": frame.get("scenario"),
        "scenario_context": {
            "id": frame.get("scenario"),
            "recognized": frame.get("scenario") in SUPPORTED_SCENARIOS,
            "policy_status": "context_only",
        },
        "sensors": sensors,
        "environment": environmental,
        "data_quality": quality,
    }
