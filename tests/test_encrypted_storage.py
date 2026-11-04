import os
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api.main import api
from backend.twin.schemas import Controls, Telemetry
from backend.twin.service import TwinService
from backend.twin.storage import (
    StorageConfigurationError,
    StorageOpenError,
    connect_database,
    settings_from_env,
)


def key() -> str:
    return os.urandom(32).hex()


def test_encrypted_database_rejects_missing_wrong_and_plaintext_access(tmp_path):
    database = str(tmp_path / "encrypted.sqlite3")
    secret = key()
    connection = connect_database(database, key=secret, encryption_required=True)
    connection.execute("CREATE TABLE records (value TEXT NOT NULL)")
    connection.execute("INSERT INTO records VALUES (?)", ("protected",))
    connection.commit()
    connection.close()

    reopened = connect_database(database, key=secret, encryption_required=True)
    assert reopened.execute("SELECT value FROM records").fetchone()[0] == "protected"
    assert reopened.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    reopened.close()

    with pytest.raises(StorageOpenError):
        connect_database(database, key=key(), encryption_required=True)
    with pytest.raises(StorageConfigurationError):
        connect_database(database, key=None, encryption_required=True)
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(database).execute("SELECT * FROM records").fetchall()


def test_wal_and_twin_records_survive_restart(tmp_path):
    database = str(tmp_path / "twin.sqlite3")
    secret = key()
    service = TwinService(
        database, encryption_required=True, database_key=secret
    )
    service.configure(
        Controls(
            source="telemetry",
            mission={"mission_id": "ENCRYPTED-MISSION"},
        )
    )
    first = service.ingest(
        Telemetry(
            timestamp=datetime.now(timezone.utc),
            sensors={
                "rpm": 4200.0,
                "egt": 1100.0,
                "cht": 390.0,
                "oil_temperature": 90.0,
                "oil_pressure": 0.1,
                "fuel_flow": 20.0,
                "vibration": 20.0,
            },
        )
    )
    approved = service.record_current_recommendation(first)
    service.decide_recommendation(
        approved["recommendation_id"], "approved", "Encrypted approval."
    )
    service.configure(
        Controls(
            source="telemetry",
            scenario="engine_degradation",
            mission={"mission_id": "ENCRYPTED-MISSION"},
        )
    )
    rejected = service.record_current_recommendation(service.snapshot())
    service.decide_recommendation(
        rejected["recommendation_id"], "rejected", "Encrypted rejection."
    )
    service.close()

    restored = TwinService(
        database, encryption_required=True, database_key=secret
    )
    assert restored.snapshot()["sequence"] > 0
    assert len(restored.history()) == 1
    assert restored.missions()[0]["mission_id"] == "ENCRYPTED-MISSION"
    assert restored.fault_history()
    tables = {
        row[0]
        for row in restored.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {
        "checkpoint",
        "history",
        "missions",
        "fault_history",
        "operator_decisions",
    } <= tables
    decisions = restored.decision_history()
    assert {item["status"] for item in decisions} == {"approved", "rejected"}
    assert {item["operator_comment"] for item in decisions} == {
        "Encrypted approval.",
        "Encrypted rejection.",
    }
    restored.close()


def test_encryption_required_fails_closed_without_key():
    with pytest.raises(StorageConfigurationError):
        connect_database(":memory:", key=None, encryption_required=True)


def test_plaintext_mode_requires_explicit_test_opt_in(monkeypatch):
    monkeypatch.setenv("TWIN_DATABASE_ENCRYPTION_REQUIRED", "false")
    monkeypatch.delenv("TWIN_DATABASE_ALLOW_PLAINTEXT_TEST_MODE", raising=False)
    with pytest.raises(StorageConfigurationError):
        settings_from_env()
    monkeypatch.setenv("TWIN_DATABASE_ALLOW_PLAINTEXT_TEST_MODE", "true")
    assert settings_from_env().encryption_required is False


def test_fastapi_startup_uses_encrypted_temporary_database(tmp_path, monkeypatch):
    monkeypatch.setenv("TWIN_DATABASE", str(tmp_path / "api.sqlite3"))
    monkeypatch.setenv("TWIN_DATABASE_KEY", key())
    monkeypatch.setenv("TWIN_DATABASE_ENCRYPTION_REQUIRED", "true")
    with TestClient(api) as client:
        assert client.get("/api/v2/health").status_code == 200
