"""Read-only Laptop 1 Protocol 1 telemetry bridge."""
import asyncio
import copy
import json
import logging
import math
import os
import threading
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import websockets
from websockets.exceptions import WebSocketException

logger = logging.getLogger(__name__)

HANDSHAKE = {"type": "hello", "client": "skynex-3d", "protocol": 1}
FRESHNESS_SECONDS = 2
RECEIVE_TIMEOUT_SECONDS = 6
REQUIRED_FIELDS = {
    "protocol",
    "seq",
    "aircraft_id",
    "mission_id",
    "scenario",
    "phase",
    "timestamp",
    "flight",
    "propulsion",
    "environment",
    "faults",
    "mission",
}


class InvalidTelemetryFrame(ValueError):
    """Raised when a Laptop 1 frame does not match the confirmed envelope."""


def _reject_json_constant(value: str) -> None:
    raise InvalidTelemetryFrame(f"Invalid JSON numeric constant: {value}")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise InvalidTelemetryFrame("Non-finite telemetry number.")
    return number


def validate_telemetry_frame(raw_frame: str | bytes) -> dict[str, Any]:
    try:
        frame = json.loads(raw_frame, parse_constant=_reject_json_constant, parse_float=_finite_float)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise InvalidTelemetryFrame("Frame is not valid JSON.") from error
    except InvalidTelemetryFrame:
        raise

    if not isinstance(frame, dict):
        raise InvalidTelemetryFrame("Frame must be a JSON object.")

    missing = REQUIRED_FIELDS - frame.keys()
    if missing:
        raise InvalidTelemetryFrame("Frame is missing required Protocol 1 fields.")
    if type(frame["protocol"]) is not int or frame["protocol"] != 1:
        raise InvalidTelemetryFrame("Protocol version must be 1.")
    if type(frame["seq"]) is not int or frame["seq"] < 0:
        raise InvalidTelemetryFrame("Sequence number must be a non-negative integer.")
    for field in ("aircraft_id", "mission_id", "scenario", "phase", "timestamp"):
        if not isinstance(frame[field], str) or not frame[field]:
            raise InvalidTelemetryFrame(f"{field} must be a non-empty string.")

    try:
        timestamp = datetime.fromisoformat(frame["timestamp"].replace("Z", "+00:00"))
    except ValueError as error:
        raise InvalidTelemetryFrame("Timestamp must be an ISO 8601 datetime.") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise InvalidTelemetryFrame("Timestamp must include a timezone.")

    for field in ("flight", "propulsion", "environment", "mission"):
        if not isinstance(frame[field], dict):
            raise InvalidTelemetryFrame(f"{field} must be a JSON object.")
    if frame["faults"] is not None and not isinstance(frame["faults"], (list, dict)):
        raise InvalidTelemetryFrame("faults must be a JSON array, object, or null.")

    return frame


def _valid_source_value(value: Any, *, allow_text: bool = False) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    return allow_text and isinstance(value, str) and bool(value.strip())


def normalize_telemetry_frame(frame: dict[str, Any]) -> dict[str, Any]:
    """Add dashboard-safe canonical fields while retaining every source field.

    The unchanged Protocol 1 frame is stored separately by the client. This copy
    retains the source names too, and records the exact source path for each
    canonical value so the UI never has to guess whether propulsion is motor or
    engine telemetry.
    """
    normalized = copy.deepcopy(frame)
    fields: dict[str, str] = {}

    def map_value(section: str, target: str, *sources: str, allow_text: bool = False) -> str | None:
        values = normalized[section]
        for source in sources:
            if source in values and _valid_source_value(values[source], allow_text=allow_text):
                values[target] = values[source]
                fields[f"{section}.{target}"] = f"{section}.{source}"
                return source
        return None

    for target, sources in {
        "altitude_m": ("altitude_m",),
        "airspeed_mps": ("airspeed_mps", "airspeed_ms"),
        "heading_deg": ("heading_deg",),
        "pitch_deg": ("pitch_deg",),
        "roll_deg": ("roll_deg",),
        "latitude": ("latitude",),
        "longitude": ("longitude",),
    }.items():
        map_value("flight", target, *sources)

    aircraft_id = frame["aircraft_id"].upper()
    rpm_sources = ("motor_rpm", "engine_rpm", "rpm") if aircraft_id == "RQ11B" else ("engine_rpm", "motor_rpm", "rpm")
    temperature_sources = (
        ("motor_temp_c", "engine_temp_c") if aircraft_id == "RQ11B"
        else ("engine_temp_c", "motor_temp_c")
    )
    rpm_source = map_value("propulsion", "rpm", *rpm_sources)
    temperature_source = map_value("propulsion", "temperature_c", *temperature_sources)
    map_value("propulsion", "battery_voltage", "battery_voltage", "battery_voltage_v")
    map_value("propulsion", "current_a", "current_a")
    map_value("propulsion", "fuel_percent", "fuel_percent", "fuel_pct")

    for target, sources in {
        "temperature_c": ("temperature_c",),
        "humidity_percent": ("humidity_percent", "humidity_pct"),
        "wind_speed_mps": ("wind_speed_mps", "wind_speed_ms"),
        "wind_direction_deg": ("wind_direction_deg", "wind_dir_deg"),
        "visibility_m": ("visibility_m",),
        "dust_level": ("dust_level", "dust"),
        "ash_level": ("ash_level", "ash"),
    }.items():
        map_value("environment", target, *sources)
    map_value("environment", "turbulence", "turbulence", allow_text=True)

    map_value("mission", "progress", "progress")
    map_value("mission", "elapsed_seconds", "elapsed_seconds", "time_s")
    map_value("mission", "current_waypoint", "current_waypoint", "wp_index")
    waypoints = normalized["mission"].get("waypoints")
    if "total_waypoints" in normalized["mission"] and _valid_source_value(normalized["mission"]["total_waypoints"]):
        fields["mission.total_waypoints"] = "mission.total_waypoints"
    elif isinstance(waypoints, list):
        normalized["mission"]["total_waypoints"] = len(waypoints)
        fields["mission.total_waypoints"] = "mission.waypoints.length"
    map_value("mission", "state", "state", allow_text=True)

    normalized["normalization"] = {
        "fields": fields,
        "rpm_kind": "motor" if rpm_source == "motor_rpm" else "engine" if rpm_source == "engine_rpm" else None,
        "temperature_kind": "motor" if temperature_source == "motor_temp_c" else "engine" if temperature_source == "engine_temp_c" else None,
    }
    return normalized


def validate_frame_order(frame, previous):
    """Shared Protocol 1 ordering boundary for live and offline providers."""
    if previous and (frame["aircraft_id"], frame["mission_id"]) == (previous["aircraft_id"], previous["mission_id"]):
        timestamp = datetime.fromisoformat(frame["timestamp"].replace("Z", "+00:00"))
        previous_timestamp = datetime.fromisoformat(previous["timestamp"].replace("Z", "+00:00"))
        if frame["seq"] <= previous["seq"] or timestamp <= previous_timestamp:
            raise InvalidTelemetryFrame("non_increasing_frame")


class Laptop1TelemetryClient:
    def __init__(
        self,
        url: str | None = None,
        *,
        connector=None,
        sleep=None,
        retry_initial_seconds: float = 1,
        retry_max_seconds: float = 30,
        receive_timeout_seconds: float = RECEIVE_TIMEOUT_SECONDS,
    ):
        self.url = url or os.getenv("LAPTOP1_TELEMETRY_WS_URL")
        self._connector = connector or websockets.connect
        self._sleep = sleep or asyncio.sleep
        self._retry_initial_seconds = retry_initial_seconds
        self._retry_max_seconds = retry_max_seconds
        self._receive_timeout_seconds = receive_timeout_seconds
        self._lock = threading.Lock()
        self._status = "disconnected"
        self._latest_frame: dict[str, Any] | None = None
        self._raw_latest_frame: dict[str, Any] | None = None
        self._last_received_at: str | None = None
        self._connected_at: str | None = None
        self._last_error: str | None = None
        self._transport_status = "disconnected"
        self._accepted_frames = 0
        self._rejected_frames = 0
        self._reconnect_attempts = 0
        self._stopping = False
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if not self.url:
            self._set_connection("disconnected", "configuration_missing")
            logger.error("LAPTOP1_TELEMETRY_WS_URL is required for Laptop 1 telemetry.")
            return
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            status = self._status
            freshness_time = self._last_received_at or self._connected_at
            if status == "connected" and freshness_time:
                received_at = datetime.fromisoformat(freshness_time)
                if (datetime.now(timezone.utc) - received_at).total_seconds() > FRESHNESS_SECONDS:
                    status = "stale"
            return {
                "status": status,
                "latest_frame": copy.deepcopy(self._latest_frame),
                "raw_latest_frame": copy.deepcopy(self._raw_latest_frame),
                "last_received_at": self._last_received_at,
                "last_error": self._last_error,
                "transport_status": self._transport_status,
                "receiver_running": self._task is not None and not self._task.done(),
                "target": self._diagnostic_target(),
                "accepted_frames": self._accepted_frames,
                "rejected_frames": self._rejected_frames,
                "reconnect_attempts": self._reconnect_attempts,
            }

    def _diagnostic_target(self) -> str | None:
        if not self.url:
            return None
        parsed = urlsplit(self.url)
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))

    def _set_connection(self, status: str, error: str | None = None) -> None:
        with self._lock:
            if status == "connected" and self._status != "connected":
                self._connected_at = datetime.now(timezone.utc).isoformat()
            elif status != "connected":
                self._connected_at = None
            self._status = status
            self._last_error = error

    def _set_transport(self, status: str) -> None:
        with self._lock:
            self._transport_status = status

    @staticmethod
    def _is_control_message(raw_frame: str | bytes) -> bool:
        try:
            message = json.loads(raw_frame)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            return False
        return isinstance(message, dict) and message.get("type") == "hello_ack" and message.get("protocol") == 1

    def _accept_frame(self, raw_frame: str | bytes, *, allow_sequence_reset: bool = False) -> bool:
        if self._is_control_message(raw_frame):
            return False
        try:
            frame = validate_telemetry_frame(raw_frame)
        except InvalidTelemetryFrame as error:
            with self._lock:
                self._rejected_frames += 1
                self._last_error = "invalid_frame"
            logger.warning("Rejected invalid Laptop 1 telemetry frame: %s", error)
            return False

        with self._lock:
            try:
                if allow_sequence_reset and self._raw_latest_frame and (
                    frame["aircraft_id"], frame["mission_id"]
                ) == (
                    self._raw_latest_frame["aircraft_id"], self._raw_latest_frame["mission_id"]
                ):
                    timestamp = datetime.fromisoformat(frame["timestamp"].replace("Z", "+00:00"))
                    previous_timestamp = datetime.fromisoformat(
                        self._raw_latest_frame["timestamp"].replace("Z", "+00:00")
                    )
                    if timestamp <= previous_timestamp:
                        raise InvalidTelemetryFrame("non_increasing_frame")
                else:
                    validate_frame_order(frame, self._raw_latest_frame)
            except InvalidTelemetryFrame:
                self._rejected_frames += 1
                self._last_error = "non_increasing_frame"
                return False
            self._raw_latest_frame = copy.deepcopy(frame)
            self._latest_frame = normalize_telemetry_frame(frame)
            self._last_received_at = datetime.now(timezone.utc).isoformat()
            if self._status != "connected":
                self._connected_at = self._last_received_at
            self._status = "connected"
            self._last_error = None
            self._accepted_frames += 1
        return True

    async def run(self) -> None:
        url = self.url
        if not url:
            self._set_connection("disconnected", "configuration_missing")
            logger.error("LAPTOP1_TELEMETRY_WS_URL is required for Laptop 1 telemetry.")
            return

        delay = self._retry_initial_seconds
        while not self._stopping:
            self._set_connection("connecting")
            self._set_transport("connecting")
            try:
                async with self._connector(
                    url, open_timeout=10, close_timeout=2
                ) as websocket:
                    self._set_transport("connected")
                    await websocket.send(json.dumps(HANDSHAKE))
                    first_valid_frame = True
                    while not self._stopping:
                        try:
                            raw_frame = await asyncio.wait_for(
                                websocket.recv(), timeout=self._receive_timeout_seconds
                            )
                        except TimeoutError:
                            self._set_connection("stale", "receive_timeout")
                            raise
                        if self._accept_frame(raw_frame, allow_sequence_reset=first_valid_frame):
                            first_valid_frame = False
                            delay = self._retry_initial_seconds
                    self._set_connection("disconnected", "connection_closed")
                    logger.info("Laptop 1 telemetry WebSocket disconnected.")
            except asyncio.CancelledError:
                self._set_transport("disconnected")
                self._set_connection("disconnected")
                raise
            except (OSError, TimeoutError, WebSocketException, ValueError) as error:
                error_name = type(error).__name__
                self._reconnect_attempts += 1
                error_code = self._last_error if self._last_error == "receive_timeout" else error_name
                self._set_connection("disconnected", error_code)
                logger.warning("Laptop 1 telemetry connection failed (%s).", error_name)
            finally:
                self._set_transport("disconnected")

            if not self._stopping:
                await self._sleep(delay)
                delay = min(delay * 2, self._retry_max_seconds)
