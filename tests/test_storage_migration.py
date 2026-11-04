import hashlib
import os
import sqlite3

import pytest

from backend.twin import storage_migration
from backend.twin.storage import (
    StorageConfigurationError,
    StorageOpenError,
    connect_database,
)
from backend.twin.storage_migration import migrate_plaintext_database


def key() -> str:
    return os.urandom(32).hex()


def digest(path):
    return hashlib.sha256(path.read_bytes()).digest()


def test_plaintext_migration_preserves_schema_records_and_source(tmp_path):
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "encrypted.sqlite3"
    plaintext = sqlite3.connect(source)
    plaintext.executescript(
        """
        CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT NOT NULL);
        CREATE INDEX records_value_idx ON records(value);
        INSERT INTO records(value) VALUES ('one'), ('two');
        """
    )
    plaintext.commit()
    plaintext.close()
    before = digest(source)

    result = migrate_plaintext_database(
        str(source), str(destination), key=key()
    )

    assert result["source_unchanged"] is True
    assert result["records"] == 2
    assert digest(source) == before
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(destination).execute("SELECT * FROM records").fetchall()


def test_migration_rejects_existing_destination(tmp_path):
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "encrypted.sqlite3"
    sqlite3.connect(source).close()
    sqlite3.connect(destination).close()
    with pytest.raises(FileExistsError):
        migrate_plaintext_database(str(source), str(destination), key=key())


@pytest.mark.parametrize("invalid_key", [None, "", "   "])
def test_migration_function_rejects_invalid_key_before_opening(
    tmp_path, invalid_key
):
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "encrypted.sqlite3"
    with pytest.raises(StorageConfigurationError):
        migrate_plaintext_database(str(source), str(destination), key=invalid_key)
    assert not source.exists()
    assert not destination.exists()


@pytest.mark.parametrize("configured_key", [None, "", "   "])
def test_migration_cli_rejects_missing_or_blank_key(
    tmp_path, monkeypatch, configured_key
):
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "encrypted.sqlite3"
    sqlite3.connect(source).close()
    if configured_key is None:
        monkeypatch.delenv("TWIN_DATABASE_KEY", raising=False)
    else:
        monkeypatch.setenv("TWIN_DATABASE_KEY", configured_key)
    monkeypatch.setattr(
        "sys.argv",
        [
            "storage_migration",
            "--source",
            str(source),
            "--destination",
            str(destination),
        ],
    )
    with pytest.raises(SystemExit) as error:
        storage_migration.main()
    assert error.value.code == 2
    assert not destination.exists()


def test_migration_cli_accepts_valid_key(tmp_path, monkeypatch):
    source = tmp_path / "source.sqlite3"
    destination = tmp_path / "encrypted.sqlite3"
    plaintext = sqlite3.connect(source)
    plaintext.execute("CREATE TABLE records (value TEXT NOT NULL)")
    plaintext.execute("INSERT INTO records VALUES (?)", ("valid-key",))
    plaintext.commit()
    plaintext.close()
    monkeypatch.setenv("TWIN_DATABASE_KEY", key())
    monkeypatch.setattr(
        "sys.argv",
        [
            "storage_migration",
            "--source",
            str(source),
            "--destination",
            str(destination),
        ],
    )
    assert storage_migration.main() == 0
    assert destination.exists()
