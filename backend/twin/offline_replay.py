"""Deterministic, isolated Protocol 1 fixture playback. Never opens a socket."""
import copy
import hashlib
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from time import monotonic
from uuid import uuid4

from .laptop1 import FRESHNESS_SECONDS, InvalidTelemetryFrame, validate_frame_order, validate_telemetry_frame

FIXTURE_PATH = Path(__file__).with_name("fixtures") / "protocol1_synthetic.json"
SCENARIOS = {
    "normal": "Normal synthetic source monitoring",
    "gnss_degraded": "GNSS DEGRADED — existing synthetic fault example",
    "stale_gap": "Stale telemetry gap and recovery",
    "missing": "No telemetry frames",
    "invalid_frame": "Missing required field and recovery",
}
SPEEDS = (0.25, 0.5, 1.0, 2.0, 4.0)


class OfflineReplay:
    def __init__(self, *, clock=monotonic):
        self.lock = threading.RLock()
        self.clock = clock
        raw = FIXTURE_PATH.read_bytes()
        self.fixture = json.loads(raw)
        self.fixture_sha256 = hashlib.sha256(raw).hexdigest()
        self.origin = datetime.fromisoformat(self.fixture["frame"]["timestamp"].replace("Z", "+00:00"))
        self.scenario = "normal"
        self.speed = 1.0
        self.duration = 30.0
        self._reset()

    def catalogue(self):
        return [{"id": key, "label": label, "synthetic": True} for key, label in SCENARIOS.items()]

    def _events(self):
        if self.scenario == "missing":
            return []
        events = []
        for offset in range(int(self.duration) + 1):
            if self.scenario == "stale_gap" and 2 <= offset < 10:
                continue
            if self.scenario == "invalid_frame" and 3 <= offset < 10:
                continue
            frame = copy.deepcopy(self.fixture["frame"])
            frame["seq"] += offset
            frame["timestamp"] = (self.origin + timedelta(seconds=offset)).isoformat()
            if self.scenario == "gnss_degraded" and offset >= 2:
                frame["faults"] = [copy.deepcopy(self.fixture["fault"])]
            if self.scenario == "invalid_frame" and offset == 2:
                del frame["propulsion"]
            events.append((float(offset), json.dumps(frame)))
        return events

    def _reset(self):
        self.session_id = str(uuid4())
        self.state = "idle"
        self.elapsed = 0.0
        self.anchor = self.clock()
        self.events = self._events()
        self.cursor = 0
        self.latest = None
        self.received_at = None
        self.last_error = None
        self.accepted = 0
        self.rejected = 0

    def _advance(self):
        current = self.clock()
        if self.state == "running":
            self.elapsed = min(self.duration, self.elapsed + max(0, current - self.anchor) * self.speed)
            while self.cursor < len(self.events) and self.events[self.cursor][0] <= self.elapsed:
                offset, raw = self.events[self.cursor]
                self.cursor += 1
                try:
                    frame = validate_telemetry_frame(raw)
                    validate_frame_order(frame, self.latest)
                except InvalidTelemetryFrame as error:
                    self.rejected += 1
                    self.last_error = "non_increasing_frame" if str(error) == "non_increasing_frame" else "invalid_frame"
                    continue
                self.latest = frame
                # Receipt is the scheduled replay time, never polling wall time.
                self.received_at = (self.origin + timedelta(seconds=offset)).isoformat()
                self.last_error = None
                self.accepted += 1
            if self.elapsed >= self.duration:
                self.state = "completed"
        self.anchor = current

    def control(self, action, *, scenario=None, speed=None):
        with self.lock:
            # Validate before changing any state, including time.
            if action not in {"start", "pause", "resume", "reset", "select", "speed"}:
                raise ValueError("Unknown replay action.")
            if action == "select" and scenario not in SCENARIOS:
                raise ValueError("Unknown replay scenario.")
            if action == "speed" and (type(speed) not in (int, float) or speed not in SPEEDS):
                raise ValueError("Replay speed must be 0.25, 0.5, 1, 2 or 4.")
            self._advance()
            if action == "start":
                if self.state != "idle":
                    raise ValueError("Reset before starting another replay; resume a paused replay.")
                self.state = "running"
            elif action == "pause":
                if self.state != "running":
                    raise ValueError("Only a running replay can be paused.")
                self.state = "paused"
            elif action == "resume":
                if self.state != "paused":
                    raise ValueError("Only a paused replay can be resumed.")
                self.state = "running"
            elif action in {"reset", "select"}:
                if scenario is not None and action == "select":
                    self.scenario = scenario
                self._reset()
            elif action == "speed":
                self.speed = float(speed)
            return self.snapshot()

    def pause_if_running(self):
        with self.lock:
            self._advance()
            if self.state == "running":
                self.state = "paused"

    def snapshot(self):
        with self.lock:
            self._advance()
            now = self.origin + timedelta(seconds=self.elapsed)
            age = (now - datetime.fromisoformat(self.latest["timestamp"])).total_seconds() if self.latest else None
            # "connected" is the shared assessment's usable-input state, not a network claim.
            status = "connected" if self.state == "running" else self.state
            if status == "connected" and age is not None and age > FRESHNESS_SECONDS:
                status = "stale"
            return {
                "mode": "OFFLINE_REPLAY", "status": status, "latest_frame": copy.deepcopy(self.latest),
                "last_received_at": self.received_at, "last_error": self.last_error,
                "replay": {"session_id": self.session_id, "state": self.state, "scenario": self.scenario,
                    "speed": self.speed, "elapsed_seconds": self.elapsed, "duration_seconds": self.duration,
                    "virtual_time": now.isoformat(), "sample_age_seconds": age,
                    "accepted_frames": self.accepted, "rejected_frames": self.rejected,
                    "fixture_id": self.fixture["fixture_id"], "fixture_sha256": self.fixture_sha256,
                    "synthetic": True, "provenance": self.fixture["provenance"],
                    "verified_live_fault_codes": self.fixture["verified_live_fault_codes"]},
            }
