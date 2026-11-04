import os

import pytest

from backend.twin.storage import StorageOpenError, connect_database
from backend.twin.storage_backup import backup_database, restore_database


def key() -> str:
    return os.urandom(32).hex()


def test_encrypted_backup_and_restore(tmp_path):
    secret = key()
    source = tmp_path / "source.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored.sqlite3"
    connection = connect_database(str(source), key=secret, encryption_required=True)
    connection.execute("CREATE TABLE records (value TEXT NOT NULL)")
    connection.execute("INSERT INTO records VALUES (?)", ("committed",))
    connection.commit()
    connection.close()

    assert backup_database(str(source), str(backup), key=secret)["integrity"] == "ok"
    assert restore_database(
        str(backup), str(restored), key=secret
    )["integrity"] == "ok"

    restored_connection = connect_database(
        str(restored), key=secret, encryption_required=True
    )
    assert restored_connection.execute(
        "SELECT value FROM records"
    ).fetchone()[0] == "committed"
    restored_connection.close()
    with pytest.raises(StorageOpenError):
        connect_database(str(backup), key=key(), encryption_required=True)
