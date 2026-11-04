"""Timestamp-safe historical trend analysis for engine telemetry.

The outputs are descriptive evidence for the Phase 4 experimental risk layer.
They are not failure probabilities, health scores, or remaining-useful-life
predictions.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from statistics import fmean, pstdev
from typing import Any


PARAMETERS = (
    "rpm",
    "engine_temperature_c",
    "battery_voltage_v",
    "electrical_current_a",
    "fuel_consumption_rate_percent_per_second",
)


@dataclass(frozen=True)
class TrendRiskConfig:
    """Experimental trend thresholds, not aircraft operating limits."""

    min_observations: int = 3
    moderate_temperature_slope: float = 0.1
    high_temperature_slope: float = 0.5
    moderate_rpm_decline: float = -10.0
    high_rpm_decline: float = -50.0
    moderate_voltage_variation: float = 0.2
    high_voltage_variation: float = 1.0
    moderate_current_variation: float = 1.0
    high_current_variation: float = 5.0
    moderate_fuel_consumption: float = 0.2
    high_fuel_consumption: float = 1.0
    moderate_warning_count: int = 2
    high_warning_count: int = 4

    def __post_init__(self) -> None:
        if self.min_observations < 2:
            raise ValueError("min_observations must be at least 2")


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _slope(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 2:
        return None
    mean_x = fmean(point[0] for point in points)
    mean_y = fmean(point[1] for point in points)
    denominator = sum((x - mean_x) ** 2 for x, _ in points)
    if denominator == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator


class HistoricalTrendAnalyzer:
    """Maintain isolated, de-duplicated streams and derive trend evidence."""

    def __init__(self, *, config: TrendRiskConfig | None = None):
        self.config = config or TrendRiskConfig()
        self._streams: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._latest: dict[tuple[str, str], datetime] = {}
        self._timestamps: dict[tuple[str, str], set[datetime]] = {}
        self._rejections: list[dict[str, Any]] = []

    @property
    def rejections(self) -> list[dict[str, Any]]:
        return list(self._rejections)

    def add(
        self,
        processed: dict[str, Any],
        *,
        assessment: dict[str, Any] | None = None,
    ) -> str:
        """Add one processed observation or return a rejection reason.

        Duplicate and out-of-order observations are retained only in the
        rejection report and never influence trend calculations.
        """

        if not isinstance(processed, dict):
            self._rejections.append({
                "reason": "invalid_processed_observation",
                "aircraft_id": None,
                "mission_id": None,
                "timestamp": None,
            })
            return "invalid_processed_observation"
        timestamp = _parse_time(processed.get("timestamp"))
        aircraft_id = processed.get("aircraft_id")
        mission_id = processed.get("mission_id")
        key = (str(aircraft_id or ""), str(mission_id or ""))
        if timestamp is None:
            return self._reject("invalid_timestamp", key, processed)
        if not aircraft_id or not mission_id:
            return self._reject("missing_identity", key, processed)
        if timestamp in self._timestamps.setdefault(key, set()):
            return self._reject("duplicate_timestamp", key, processed)
        if key in self._latest and timestamp <= self._latest[key]:
            return self._reject("out_of_order", key, processed)

        features = processed.get("features") or {}
        values = {
            parameter: features.get(parameter)
            for parameter in PARAMETERS
        }
        warnings = []
        if assessment:
            warnings = [
                item.get("rule_id")
                for item in assessment.get("findings", [])
                if item.get("status") in {"WARNING", "CRITICAL"}
            ]
        observation = {
            "timestamp": timestamp,
            "timestamp_text": processed.get("timestamp"),
            "aircraft_id": aircraft_id,
            "mission_id": mission_id,
            "scenario_id": processed.get("scenario_id"),
            "values": values,
            "warnings": tuple(sorted(item for item in warnings if item)),
            "synthetic": (
                processed.get("raw_telemetry", {}).get("synthetic")
                if isinstance(processed.get("raw_telemetry"), dict)
                else None
            ),
            "provenance": (
                processed.get("raw_telemetry", {}).get("provenance")
                if isinstance(processed.get("raw_telemetry"), dict)
                else None
            ),
        }
        self._streams.setdefault(key, []).append(observation)
        self._timestamps[key].add(timestamp)
        self._latest[key] = timestamp
        return "accepted"

    def analyze(
        self,
        *,
        aircraft_id: str,
        mission_id: str,
    ) -> list[dict[str, Any]]:
        """Return one explainable experimental risk assessment per parameter."""

        key = (aircraft_id, mission_id)
        observations = self._streams.get(key, [])
        if not observations:
            return [self._assessment(
                observations, key, "telemetry", "INSUFFICIENT_DATA",
                "No accepted observations are available for this aircraft and mission.",
                None,
            )]

        results = [
            self._analyze_parameter(observations, key, parameter)
            for parameter in PARAMETERS
        ]
        warning_result = self._analyze_warnings(observations, key)
        if warning_result is not None:
            results.append(warning_result)
        return results

    def _reject(
        self,
        reason: str,
        key: tuple[str, str],
        processed: dict[str, Any],
    ) -> str:
        self._rejections.append({
            "reason": reason,
            "aircraft_id": key[0],
            "mission_id": key[1],
            "timestamp": processed.get("timestamp"),
        })
        return reason

    def _analyze_parameter(
        self,
        observations: list[dict[str, Any]],
        key: tuple[str, str],
        parameter: str,
    ) -> dict[str, Any]:
        points = [
            ((item["timestamp"] - observations[0]["timestamp"]).total_seconds(), float(item["values"][parameter]))
            for item in observations
            if _finite(item["values"].get(parameter))
        ]
        if len(points) < self.config.min_observations:
            return self._assessment(
                observations, key, parameter, "INSUFFICIENT_DATA",
                f"{parameter} has {len(points)} valid observations; "
                f"{self.config.min_observations} are required for a trend.",
                {"valid_observations": len(points)},
            )

        slope = _slope(points)
        variation = pstdev(point[1] for point in points) if len(points) > 1 else None
        risk = "LOW"
        reason = f"{parameter} has sufficient history and no configured experimental deterioration pattern."
        if parameter == "engine_temperature_c" and slope is not None:
            risk, reason = self._directional_risk(
                slope, self.config.moderate_temperature_slope,
                self.config.high_temperature_slope,
                f"temperature increased at {slope:.4g} °C/s",
                positive=True,
            )
        elif parameter == "rpm" and slope is not None:
            risk, reason = self._directional_risk(
                slope, self.config.moderate_rpm_decline,
                self.config.high_rpm_decline,
                f"RPM declined at {slope:.4g} rpm/s",
                positive=False,
            )
        elif parameter == "battery_voltage_v" and variation is not None:
            risk, reason = self._magnitude_risk(
                variation, self.config.moderate_voltage_variation,
                self.config.high_voltage_variation,
                f"voltage variation was {variation:.4g} V",
            )
        elif parameter == "electrical_current_a" and variation is not None:
            risk, reason = self._magnitude_risk(
                variation, self.config.moderate_current_variation,
                self.config.high_current_variation,
                f"current variation was {variation:.4g} A",
            )
        elif parameter == "fuel_consumption_rate_percent_per_second" and slope is not None:
            risk, reason = self._magnitude_risk(
                fmean(point[1] for point in points),
                self.config.moderate_fuel_consumption,
                self.config.high_fuel_consumption,
                f"fuel consumption rate averaged {fmean(point[1] for point in points):.4g} %/s",
            )
        return self._assessment(
            observations, key, parameter, risk, reason,
            {
                "valid_observations": len(points),
                "slope": slope,
                "variation": variation,
                "first_value": points[0][1],
                "last_value": points[-1][1],
            },
        )

    def _analyze_warnings(
        self,
        observations: list[dict[str, Any]],
        key: tuple[str, str],
    ) -> dict[str, Any] | None:
        warning_events = [
            (item["timestamp"], warning)
            for item in observations
            for warning in item["warnings"]
        ]
        if not warning_events:
            return None
        count = len(warning_events)
        if count >= self.config.high_warning_count:
            risk = "HIGH"
        elif count >= self.config.moderate_warning_count:
            risk = "MODERATE"
        else:
            risk = "LOW"
        first = warning_events[0][0]
        latest = warning_events[-1][0]
        return self._assessment(
            observations, key, "engineering_warnings", risk,
            f"{count} engineering warning event(s) persisted across "
            f"{(latest - first).total_seconds():.4g} seconds.",
            {
                "warning_count": count,
                "rule_ids": sorted({rule_id for _, rule_id in warning_events}),
                "first_warning_timestamp": first.isoformat(),
                "last_warning_timestamp": latest.isoformat(),
            },
        )

    @staticmethod
    def _directional_risk(
        value: float,
        moderate: float,
        high: float,
        description: str,
        *,
        positive: bool,
    ) -> tuple[str, str]:
        triggered = value >= 0 if positive else value <= 0
        magnitude = value if positive else -value
        if not triggered:
            return "LOW", "The observed direction does not match the configured deterioration pattern."
        if magnitude >= abs(high):
            return "HIGH", description + " (high experimental trend band)."
        if magnitude >= abs(moderate):
            return "MODERATE", description + " (moderate experimental trend band)."
        return "LOW", description + " but remains below the moderate experimental trend band."

    @staticmethod
    def _magnitude_risk(
        value: float,
        moderate: float,
        high: float,
        description: str,
    ) -> tuple[str, str]:
        if value >= high:
            return "HIGH", description + " (high experimental variation band)."
        if value >= moderate:
            return "MODERATE", description + " (moderate experimental variation band)."
        return "LOW", description + " but remains below the moderate experimental band."

    def _assessment(
        self,
        observations: list[dict[str, Any]],
        key: tuple[str, str],
        parameter: str,
        risk: str,
        explanation: str,
        evidence: dict[str, Any] | None,
    ) -> dict[str, Any]:
        latest = observations[-1] if observations else None
        first = observations[0] if observations else None
        duration = (
            (latest["timestamp"] - first["timestamp"]).total_seconds()
            if latest and first else None
        )
        provenance = {
            "synthetic": latest.get("synthetic") if latest else None,
            "source": latest.get("provenance") if latest else None,
            "assessment_kind": "experimental_trend_indicator",
        }
        identity = {
            "aircraft_id": key[0],
            "mission_id": key[1],
            "parameter": parameter,
            "timestamp": latest.get("timestamp_text") if latest else None,
            "model_version": "experimental-trend-risk-1.0",
        }
        assessment_id = hashlib.sha256(
            json.dumps(identity, sort_keys=True).encode("utf-8")
        ).hexdigest()[:32]
        return {
            "assessment_id": assessment_id,
            "aircraft_id": key[0],
            "mission_id": key[1],
            "timestamp": latest.get("timestamp_text") if latest else None,
            "scenario_id": latest.get("scenario_id") if latest else None,
            "parameter": parameter,
            "observed_trend": evidence,
            "risk_category": risk,
            "data_sufficiency": {
                "accepted_observations": len(observations),
                "duration_seconds": duration,
                "minimum_observations": self.config.min_observations,
                "sufficient": risk not in {"INSUFFICIENT_DATA", "NOT_ASSESSED"},
            },
            "explanation": explanation,
            "historical_evidence": {
                "first_timestamp": first.get("timestamp_text") if first else None,
                "last_timestamp": latest.get("timestamp_text") if latest else None,
                "scenario_ids": sorted({item.get("scenario_id") for item in observations}),
            },
            "model_version": "experimental-trend-risk-1.0",
            "provenance": provenance,
            "limitations": [
                "No labelled engine-fault dataset was available for supervised validation.",
                "This is not a failure probability, health score, or RUL estimate.",
            ],
        }
