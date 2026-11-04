from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class Sensors(StrictModel):
    rpm: float = Field(ge=0, le=7000)
    egt: float = Field(ge=-50, le=1200)
    cht: float = Field(ge=-50, le=400)
    oil_temperature: float = Field(ge=-50, le=250)
    oil_pressure: float = Field(ge=0, le=12)
    fuel_flow: float = Field(ge=0, le=80)
    vibration: float = Field(ge=0, le=50)


class Mission(StrictModel):
    mission_id: str = Field(default="MISSION-ALPHA")
    duration_hours: float = Field(default=8.0, ge=0.25, le=48)
    environmental_severity: float = Field(default=0.3, ge=0, le=1)


class Controls(StrictModel):
    rpm_target: float = Field(default=4800.0, ge=2000, le=5800)
    ambient_temperature: float = Field(default=25.0, ge=-20, le=55)
    fuel_flow_multiplier: float = Field(default=1.0, ge=0.7, le=1.3)
    scenario: Literal["nominal", "engine_degradation", "sensor_bias", "fuel_leak", "compressor_fouling", "engine_overheating", "cooling_loss", "oil_leak", "sensor_drift", "bearing_wear", "fuel_restriction"] = "nominal"
    running: bool = True
    source: Literal["simulation", "telemetry"] = "simulation"
    mission: Mission = Field(default_factory=Mission)


class Telemetry(StrictModel):
    timestamp: AwareDatetime = Field(strict=False)
    sensors: Sensors


class WhatIf(StrictModel):
    rpm_adjustment: float = Field(default=0.0, ge=-1500, le=1500)
    temperature_variation: float = Field(default=0.0, ge=-20, le=30)
    fuel_flow_variation: float = Field(default=0.0, ge=-30, le=30)
    horizon_minutes: float = Field(default=15.0, ge=1, le=60)


class DemoReset(StrictModel):
    """A deterministic reset for the judge-facing simulation walkthrough."""
    scenario: Literal["nominal", "engine_degradation", "sensor_bias", "fuel_leak", "compressor_fouling"] = "nominal"


class OperatorDecisionSubmission(StrictModel):
    status: Literal["approved", "rejected"]
    operator_comment: str = Field(min_length=1, max_length=2000)

    @field_validator("operator_comment")
    @classmethod
    def comment_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Operator comment must not be blank.")
        return value


class TelemetrySourceSelection(StrictModel):
    mode: Literal["LIVE_LAPTOP1", "OFFLINE_REPLAY"]


class ReplayControl(StrictModel):
    action: Literal["start", "pause", "resume", "reset", "select", "speed"]
    scenario: Literal["normal", "gnss_degraded", "stale_gap", "missing", "invalid_frame"] | None = None
    speed: float | None = None

    @model_validator(mode="after")
    def valid_action_arguments(self):
        if (self.action == "select") != (self.scenario is not None):
            raise ValueError("Only select requires a scenario.")
        if (self.action == "speed") != (self.speed is not None):
            raise ValueError("Only speed requires a speed value.")
        if self.speed is not None and self.speed not in (0.25, 0.5, 1, 2, 4):
            raise ValueError("Supported speeds: 0.25, 0.5, 1, 2, 4.")
        return self
