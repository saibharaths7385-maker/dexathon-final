import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.twin.laptop1 import (
    HANDSHAKE,
    InvalidTelemetryFrame,
    Laptop1TelemetryClient,
    normalize_telemetry_frame,
    validate_telemetry_frame,
)


def valid_frame(**updates):
    frame = {
        "protocol": 1,
        "seq": 7,
        "aircraft_id": "EAGLE_EYE_MINI",
        "mission_id": "MISSION-DEMO",
        "scenario": "coastal",
        "phase": "cruise",
        "timestamp": "2026-11-04T10:40:00Z",
        "flight": {"altitude_m": 1200},
        "propulsion": {"engine_temp_c": 190, "battery_voltage": 14.2},
        "environment": {"wind_speed": 5},
        "faults": [],
        "mission": {"progress": 0.6},
    }
    frame.update(updates)
    return frame


def test_valid_frame_preserves_protocol_fields_and_values():
    frame = valid_frame()
    assert validate_telemetry_frame(json.dumps(frame)) == frame


@pytest.mark.parametrize(
    "raw_frame",
    [
        "{not json",
        "[]",
        json.dumps({key: value for key, value in valid_frame().items() if key != "flight"}),
        json.dumps(valid_frame(protocol=2)),
        json.dumps(valid_frame(seq=True)),
        json.dumps(valid_frame(seq=-1)),
        json.dumps(valid_frame(timestamp="2026-11-04T10:40:00")),
        '{"protocol":NaN}',
    ],
)
def test_invalid_frames_are_rejected(raw_frame):
    with pytest.raises(InvalidTelemetryFrame):
        validate_telemetry_frame(raw_frame)


def test_invalid_frame_does_not_replace_latest_valid_frame():
    client = Laptop1TelemetryClient("ws://127.0.0.1:8000/ws/test")
    frame = valid_frame()

    client._accept_frame(json.dumps(frame))
    client._accept_frame("{not json")

    result = client.snapshot()
    assert result["latest_frame"] == normalize_telemetry_frame(frame)
    assert result["raw_latest_frame"] == frame
    assert result["last_error"] == "invalid_frame"
    assert result["status"] == "connected"


def test_connection_status_becomes_stale_when_frames_stop():
    client = Laptop1TelemetryClient("ws://127.0.0.1:8000/ws/test")
    client._accept_frame(json.dumps(valid_frame()))
    client._last_received_at = (
        datetime.now(timezone.utc) - timedelta(seconds=3)
    ).isoformat()

    assert client.snapshot()["status"] == "stale"


def test_missing_websocket_url_is_reported_without_connecting(monkeypatch):
    monkeypatch.delenv("LAPTOP1_TELEMETRY_WS_URL", raising=False)
    client = Laptop1TelemetryClient()

    client.start()

    result = client.snapshot()
    assert result["status"] == "disconnected"
    assert result["latest_frame"] is None
    assert result["raw_latest_frame"] is None
    assert result["last_received_at"] is None
    assert result["last_error"] == "configuration_missing"
    assert result["receiver_running"] is False


class FakeSocket:
    def __init__(self, frames):
        self.frames = frames
        self.sent = []

    async def send(self, payload):
        self.sent.append(payload)

    async def recv(self):
        if self.frames:
            return self.frames.pop(0)
        raise TimeoutError("no more frames")


class FakeConnection:
    def __init__(self, socket=None, error=None):
        self.socket = socket
        self.error = error

    async def __aenter__(self):
        if self.error:
            raise self.error
        return self.socket

    async def __aexit__(self, *_args):
        return False


def test_disconnect_reconnects_and_receives_latest_frame():
    frame = valid_frame(seq=8)
    socket = FakeSocket([json.dumps(frame)])
    connections = [
        FakeConnection(error=ConnectionRefusedError("offline")),
        FakeConnection(socket=socket),
    ]
    attempts = []
    delays = []
    client = None

    def connector(url, **_kwargs):
        attempts.append(url)
        return connections[len(attempts) - 1]

    async def sleep(delay):
        delays.append(delay)
        if len(delays) == 2:
            client._stopping = True

    client = Laptop1TelemetryClient(
        "ws://simulator.test/ws/telemetry",
        connector=connector,
        sleep=sleep,
    )
    asyncio.run(client.run())

    assert len(attempts) == 2
    assert delays == [1, 1]
    assert json.loads(socket.sent[0]) == HANDSHAKE
    assert client.snapshot()["latest_frame"] == normalize_telemetry_frame(frame)
    assert client.snapshot()["raw_latest_frame"] == frame
    assert client.snapshot()["last_received_at"] is not None
    assert client.snapshot()["status"] == "disconnected"


def test_hello_ack_is_control_message_not_invalid_telemetry():
    client = Laptop1TelemetryClient("ws://127.0.0.1:8000/ws/test")
    assert client._accept_frame(json.dumps({"type": "hello_ack", "protocol": 1})) is False
    result = client.snapshot()
    assert result["last_error"] is None
    assert result["rejected_frames"] == 0


def test_eagle_eye_frame_normalizes_exact_source_fields_and_retains_raw():
    frame = valid_frame(
        flight={"airspeed_ms": 42},
        propulsion={
            "engine_rpm": 4800,
            "engine_temp_c": 190,
            "battery_voltage_v": 14.2,
            "current_a": 12.3,
            "fuel_pct": 74,
        },
        environment={
            "humidity_pct": 55,
            "wind_speed_ms": 5,
            "wind_dir_deg": 220,
            "dust": 0.1,
            "ash": 0,
        },
        mission={"time_s": 345, "state": "CRUISE", "progress": .6, "wp_index": 2, "waypoints": [{}, {}, {}]},
    )
    client = Laptop1TelemetryClient("ws://127.0.0.1:8000/ws/test")
    assert client._accept_frame(json.dumps(frame)) is True
    result = client.snapshot()
    normalized = result["latest_frame"]
    assert result["raw_latest_frame"] == frame
    assert normalized["flight"]["airspeed_mps"] == 42
    assert {key: normalized["propulsion"][key] for key in (
        "rpm", "temperature_c", "battery_voltage", "current_a", "fuel_percent"
    )} == {
        "rpm": 4800, "temperature_c": 190, "battery_voltage": 14.2,
        "current_a": 12.3, "fuel_percent": 74,
    }
    assert {key: normalized["environment"][key] for key in (
        "humidity_percent", "wind_speed_mps", "wind_direction_deg", "dust_level", "ash_level"
    )} == {
        "humidity_percent": 55, "wind_speed_mps": 5,
        "wind_direction_deg": 220, "dust_level": .1, "ash_level": 0,
    }
    assert normalized["mission"]["elapsed_seconds"] == 345
    assert normalized["mission"]["current_waypoint"] == 2
    assert normalized["mission"]["total_waypoints"] == 3
    assert normalized["normalization"]["rpm_kind"] == "engine"
    assert normalized["normalization"]["fields"]["propulsion.rpm"] == "propulsion.engine_rpm"


def test_rq11b_motor_channels_remain_motor_specific():
    frame = valid_frame(
        aircraft_id="RQ11B",
        propulsion={"motor_rpm": 5100, "motor_temp_c": 61, "battery_voltage_v": 15.4},
    )
    normalized = normalize_telemetry_frame(frame)
    assert normalized["propulsion"]["rpm"] == 5100
    assert normalized["propulsion"]["temperature_c"] == 61
    assert normalized["normalization"]["rpm_kind"] == "motor"
    assert normalized["normalization"]["temperature_kind"] == "motor"
    assert "engine_temp_c" not in normalized["propulsion"]


def test_normalization_does_not_promote_invalid_metric_values():
    frame = valid_frame(
        flight={"airspeed_ms": "fast"},
        propulsion={"engine_rpm": True, "fuel_pct": None},
        environment={"humidity_pct": "wet"},
    )
    normalized = normalize_telemetry_frame(frame)
    assert "airspeed_mps" not in normalized["flight"]
    assert "rpm" not in normalized["propulsion"]
    assert "fuel_percent" not in normalized["propulsion"]
    assert "humidity_percent" not in normalized["environment"]


def test_first_frame_after_reconnect_may_reset_sequence_but_not_timestamp():
    client = Laptop1TelemetryClient("ws://127.0.0.1:8000/ws/test")
    assert client._accept_frame(json.dumps(valid_frame(seq=100)))
    restarted = valid_frame(seq=0, timestamp="2026-11-04T10:40:01Z")
    assert client._accept_frame(json.dumps(restarted), allow_sequence_reset=True)
    assert client.snapshot()["raw_latest_frame"] == restarted

    replayed = valid_frame(seq=0, timestamp="2026-11-04T10:40:00Z")
    assert not client._accept_frame(json.dumps(replayed), allow_sequence_reset=True)
    assert client.snapshot()["raw_latest_frame"] == restarted
