"""Feature extraction for preprocessed engine telemetry.

Features are descriptive inputs for later rule/model components. This module
does not assign fault labels, health scores, probabilities, or RUL.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from statistics import fmean, pstdev
from typing import Any

from .telemetry_preprocessing import preprocess_normalized_frame


def _time(value: str | None) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None


class FeatureEngineer:
    """Extract current and history-derived features from normalized frames."""

    def __init__(self, *, window_size: int = 5):
        if not isinstance(window_size, int) or window_size < 2:
            raise ValueError("window_size must be an integer greater than one")
        self.window_size = window_size
        self._history: deque[dict[str, Any]] = deque(maxlen=window_size)

    def process(self, frame: dict[str, Any]) -> dict[str, Any]:
        processed = preprocess_normalized_frame(frame)
        current = processed["sensors"]
        previous = self._history[-1] if self._history else None
        timestamp = _time(processed.get("timestamp"))
        previous_time = _time(previous.get("timestamp")) if previous else None
        elapsed = (timestamp - previous_time).total_seconds() if timestamp and previous_time else None
        comparable = elapsed is not None and elapsed > 0 and (
            previous.get("aircraft_id") == processed.get("aircraft_id")
            and previous.get("mission_id") == processed.get("mission_id")
        )

        def value(name: str) -> float | None:
            item = current[name]
            return item["value"] if item["status"] == "valid" else None

        def prior_value(name: str) -> float | None:
            if not comparable:
                return None
            item = previous["sensors"][name]
            return item["value"] if item["status"] == "valid" else None

        def rate(name: str) -> float | None:
            old, new = prior_value(name), value(name)
            return (new - old) / elapsed if old is not None and new is not None and elapsed else None

        features: dict[str, Any] = {
            "rpm": value("rpm"),
            "engine_temperature_c": value("engine_temperature"),
            "battery_voltage_v": value("battery_voltage"),
            "electrical_current_a": value("electrical_current"),
            "fuel_percent": value("fuel_percent"),
            "rpm_change_per_second": rate("rpm"),
            "temperature_change_per_second": rate("engine_temperature"),
            "voltage_change_per_second": rate("battery_voltage"),
            "fuel_consumption_rate_percent_per_second": (
                -rate("fuel_percent") if rate("fuel_percent") is not None else None
            ),
            "history_samples": len(self._history),
            "rolling": self._rolling_features(),
            "data_quality": processed["data_quality"],
        }
        if processed["accepted"]:
            self._history.append(processed)
        return {
            **processed,
            "features": features,
            "feature_quality": {
                "has_consecutive_frame": comparable,
                "elapsed_seconds": elapsed if comparable else None,
                "rolling_window_size": self.window_size,
                "rolling_ready": len(self._history) >= self.window_size - 1,
            },
        }

    def _rolling_features(self) -> dict[str, float | None]:
        if len(self._history) < self.window_size - 1:
            return {
                "rpm_moving_average": None,
                "temperature_moving_average_c": None,
                "voltage_variation_v": None,
                "fuel_moving_average_percent": None,
            }

        def values(name: str) -> list[float]:
            return [
                item["sensors"][name]["value"]
                for item in self._history
                if item["sensors"][name]["status"] == "valid"
            ]

        rpm, temperature = values("rpm"), values("engine_temperature")
        voltage, fuel = values("battery_voltage"), values("fuel_percent")
        return {
            "rpm_moving_average": fmean(rpm) if rpm else None,
            "temperature_moving_average_c": fmean(temperature) if temperature else None,
            "voltage_variation_v": pstdev(voltage) if len(voltage) > 1 else None,
            "fuel_moving_average_percent": fmean(fuel) if fuel else None,
        }
