import asyncio
import copy
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.twin.decision_support import evaluate, protocol1_recommendations
from backend.twin.laptop1 import Laptop1TelemetryClient
from backend.twin.offline_replay import OfflineReplay, SCENARIOS
from backend.twin.service import TwinService
from backend.twin.telemetry_sources import TelemetrySources


class Clock:
    time = 0.0

    def __call__(self):
        return self.time

    def advance(self, seconds):
        self.time += seconds


@pytest.fixture
def replay():
    clock = Clock()
    return OfflineReplay(clock=clock), clock


def test_normal_frames_use_existing_values_and_relative_time(replay):
    player, clock = replay
    first = player.control("start")
    clock.advance(2.5)
    latest = player.snapshot()
    assert latest["latest_frame"]["seq"] == first["latest_frame"]["seq"] + 2
    assert latest["replay"]["accepted_frames"] == 3
    assert latest["replay"]["sample_age_seconds"] == .5
    assert latest["latest_frame"]["propulsion"] == player.fixture["frame"]["propulsion"]
    assert latest["replay"]["synthetic"] is True
    assert latest["replay"]["verified_live_fault_codes"] == []
    assert latest["mode"] == "OFFLINE_REPLAY"


def test_same_clock_produces_same_frames_independent_of_poll_frequency():
    clock = Clock()
    first, second = OfflineReplay(clock=clock), OfflineReplay(clock=clock)
    first.control("start")
    second.control("start")
    for _ in range(5):
        clock.advance(1)
        first.snapshot()
    assert first.snapshot()["latest_frame"] == second.snapshot()["latest_frame"]
    assert first.snapshot()["replay"]["accepted_frames"] == second.snapshot()["replay"]["accepted_frames"]


def test_fault_fixture_uses_shared_assessment(replay):
    player, clock = replay
    player.control("select", scenario="gnss_degraded")
    player.control("start")
    clock.advance(2)
    state = player.snapshot()
    virtual_now = datetime.fromisoformat(state["replay"]["virtual_time"])
    direct = protocol1_recommendations(state, virtual_now)[0]["recommendation_details"]
    result = evaluate(None, state, datetime.now(timezone.utc))[0]
    assert result["source"] == "OFFLINE_REPLAY"
    assert result["recommendation_details"]["rule_id"] == "protocol1.source_faults"
    assert result["recommendation_details"]["evidence"] == direct["evidence"]
    assert state["latest_frame"]["faults"] == [player.fixture["fault"]]
    assert result["recommendation_details"]["replay_session_id"] == player.session_id


def test_pause_resume_speed_reset_and_scenario_transition(replay):
    player, clock = replay
    started = player.control("start")
    clock.advance(1)
    paused = player.control("pause")
    clock.advance(50)
    assert player.snapshot() == paused
    player.control("speed", speed=2)
    player.control("resume")
    clock.advance(2)
    assert player.snapshot()["replay"]["elapsed_seconds"] == 5
    reset = player.control("reset")
    assert reset["latest_frame"] is None and reset["replay"]["state"] == "idle"
    assert reset["replay"]["session_id"] != started["replay"]["session_id"]
    selected = player.control("select", scenario="missing")
    assert selected["replay"]["session_id"] != reset["replay"]["session_id"]
    assert selected["latest_frame"] is None
    assert selected["replay"]["scenario"] == "missing"


@pytest.mark.parametrize("speed", [0.25, 0.5, 1, 2, 4])
def test_speed_scales_virtual_time_without_altering_frame_values(replay, speed):
    player, clock = replay
    player.control("speed", speed=speed)
    player.control("start")
    clock.advance(4)
    state = player.snapshot()
    assert state["replay"]["elapsed_seconds"] == 4 * speed
    assert state["replay"]["accepted_frames"] == int(4 * speed) + 1


@pytest.mark.parametrize("scenario,at,quality", [
    ("missing", 4, "missing"), ("stale_gap", 4, "stale"),
    ("invalid_frame", 2, "invalid_frame"), ("normal", 30, "completed"),
])
def test_quality_cases_suppress_condition_advice(replay, scenario, at, quality):
    player, clock = replay
    player.control("select", scenario=scenario)
    player.control("start")
    clock.advance(at)
    state = player.snapshot()
    result = evaluate(None, state, datetime.now(timezone.utc))
    assert len(result) == 1
    assert result[0]["recommendation_details"]["quality"] == quality
    if scenario == "invalid_frame":
        assert state["replay"]["rejected_frames"] == 1
        assert state["latest_frame"]["seq"] == 8
    if scenario in {"stale_gap", "invalid_frame"}:
        clock.advance(10 - at)
        assert player.snapshot()["last_error"] is None
        assert evaluate(None, player.snapshot(), datetime.now(timezone.utc))[0]["recommendation_details"]["rule_id"] == "protocol1.no_reported_faults"


def test_pause_is_explicitly_not_fresh_condition(replay):
    player, _ = replay
    player.control("start")
    state = player.control("pause")
    assert evaluate(None, state, datetime.now(timezone.utc))[0]["recommendation_details"]["quality"] == "paused"


@pytest.mark.parametrize("mutation", ["protocol", "missing", "seq", "time", "nan"])
def test_invalid_frames_cannot_replace_last_good_sample(replay, mutation):
    player, clock = replay
    initial = player.control("start")["latest_frame"]
    bad = copy.deepcopy(initial)
    if mutation == "protocol":
        bad["protocol"] = 2
    elif mutation == "missing":
        del bad["mission_id"]
    elif mutation == "seq":
        bad["seq"] -= 1
    elif mutation == "time":
        bad["seq"] += 1  # same source timestamp is out of order
    else:
        bad["propulsion"]["rpm"] = float("nan")
    player.events.insert(player.cursor, (.5, json.dumps(bad)))
    clock.advance(.5)
    state = player.snapshot()
    assert state["latest_frame"] == initial
    assert state["last_received_at"] == initial["timestamp"]
    assert state["replay"]["rejected_frames"] == 1


def test_source_switching_never_mixes_state_or_opens_socket_offline():
    class Live:
        starts = 0
        stops = 0
        def start(self):
            self.starts += 1
        async def stop(self):
            self.stops += 1
        def snapshot(self):
            return {"status": "disconnected", "latest_frame": {"seq": 999}}
    live = Live()
    sources = TelemetrySources(live, "OFFLINE_REPLAY")
    sources.start()
    assert live.starts == 0
    sources.replay.control("start")
    session = sources.replay.session_id
    assert sources.snapshot()["latest_frame"]["seq"] == 7
    assert asyncio.run(sources.select("LIVE_LAPTOP1"))["latest_frame"]["seq"] == 999
    assert sources.replay.state == "paused"
    offline = asyncio.run(sources.select("OFFLINE_REPLAY"))
    assert offline["latest_frame"]["seq"] == 7
    assert offline["replay"]["session_id"] == session
    assert live.starts == live.stops == 1


def test_decision_provenance_dedup_restart_and_existing_rows(tmp_path, replay):
    player, _ = replay
    database = str(tmp_path / "decisions.sqlite3")
    service = TwinService(database)
    legacy = service.record_current_recommendation(service.snapshot())
    original_state = copy.deepcopy(service.state)
    state = player.control("start")
    first = service.scenario_recommendations(state)["recommendations"][0]
    repeated = service.scenario_recommendations(state)["recommendations"][0]
    assert first["recommendation_id"] == repeated["recommendation_id"]
    service.decide_recommendation(first["recommendation_id"], "approved", "Synthetic review.")
    player.control("reset")
    second = service.scenario_recommendations(player.control("start"))["recommendations"][0]
    assert second["recommendation_id"] != first["recommendation_id"]
    service.decide_recommendation(second["recommendation_id"], "rejected", "Second session rejected.")
    assert service.state == original_state and service.sequence == 0 and service.history() == []
    service.close()
    restored = TwinService(database)
    try:
        rows = {row["recommendation_id"]: row for row in restored.decision_history()}
        assert rows[legacy["recommendation_id"]] == legacy
        assert rows[first["recommendation_id"]]["status"] == "approved"
        assert rows[second["recommendation_id"]]["status"] == "rejected"
        assert rows[first["recommendation_id"]]["recommendation_details"]["replay_session_id"] == state["replay"]["session_id"]
    finally:
        restored.close()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TWIN_DATABASE", ":memory:")
    monkeypatch.setenv("SKYNEX_DATA_SOURCE", "OFFLINE_REPLAY")
    def no_live_start(_self):
        pytest.fail("Offline startup must not start the live provider")
    monkeypatch.setattr(Laptop1TelemetryClient, "start", no_live_start)
    with TestClient(app) as client:
        yield client


def test_offline_api_controls_evaluation_and_history(client):
    assert client.get("/api/v2/telemetry/source").json()["mode"] == "OFFLINE_REPLAY"
    assert {item["id"] for item in client.get("/api/v2/replay").json()["scenarios"]} == set(SCENARIOS)
    assert client.post("/api/v2/replay/control", json={"action": "start"}).status_code == 200
    result = client.post("/api/v2/recommendations/evaluate").json()
    assert result["source_mode"] == "OFFLINE_REPLAY"
    record = result["recommendations"][0]
    assert record["source"] == "OFFLINE_REPLAY"
    assert client.get("/api/v2/laptop1").json()["latest_frame"] is None
    path = f"/api/v2/recommendations/{record['recommendation_id']}/decision"
    assert client.post(path, json={"status": "approved", "operator_comment": "Offline only"}).status_code == 200
    assert client.post(path, json={"status": "rejected", "operator_comment": "Duplicate"}).status_code == 409
    assert client.get("/api/v2/twin").json()["sequence"] == 0


@pytest.mark.parametrize("body", [
    {"action": "start", "scenario": "normal"}, {"action": "select"},
    {"action": "select", "scenario": "invented"}, {"action": "speed", "speed": True},
    {"action": "speed", "speed": 100}, {"action": "speed", "speed": "2"}, {"action": "command"},
])
def test_invalid_controls_do_not_mutate_session(client, body):
    before = client.get("/api/v2/replay").json()
    assert client.post("/api/v2/replay/control", json=body).status_code == 422
    assert client.get("/api/v2/replay").json() == before
