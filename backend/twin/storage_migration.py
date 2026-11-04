"""Explicit plaintext SQLite to SQLCipher migration utilities."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from typing import Any

from .storage import (
    StorageOpenError,
    _load_sqlcipher,
    _quote_pragma_string,
    _require_key,
    connect_database,
)


def _schema(connection: Any) -> list[tuple[str, str, str]]:
    return connection.execute(
        """SELECT type, name, sql FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"""
    ).fetchall()


def _table_counts(connection: Any) -> dict[str, int]:
    tables = connection.execute(
        """SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"""
    ).fetchall()
    return {
        table[0]: connection.execute(
            f'SELECT count(*) FROM "{table[0].replace(chr(34), chr(34) * 2)}"'
        ).fetchone()[0]
        for table in tables
    }


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def migrate_plaintext_database(
    source_path: str,
    destination_path: str,
    *,
    key: str,
) -> dict[str, object]:
    """Create and verify an encrypted copy without changing the source."""
    key = _require_key(key)
    source = Path(source_path)
    destination = Path(destination_path)
    if source.resolve() == destination.resolve():
        raise ValueError("Migration source and destination must be different.")
    if not source.exists():
        raise FileNotFoundError("Migration source database does not exist.")
    if destination.exists():
        raise FileExistsError("Migration destination already exists.")

    source_digest = _file_digest(source)
    plaintext = _load_sqlcipher().connect(str(source))
    encrypted = None
    try:
        source_integrity = plaintext.execute("PRAGMA integrity_check").fetchone()
        if not source_integrity or source_integrity[0] != "ok":
            raise StorageOpenError("Plaintext source database integrity check failed.")
        source_schema = _schema(plaintext)
        source_counts = _table_counts(plaintext)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination_sql = _quote_pragma_string(str(destination))
        key_sql = _quote_pragma_string(key)
        plaintext.execute(
            f"ATTACH DATABASE '{destination_sql}' AS encrypted KEY '{key_sql}'"
        )
        plaintext.execute("SELECT sqlcipher_export('encrypted')")
        plaintext.execute("DETACH DATABASE encrypted")
        plaintext.close()
        plaintext = None
        encrypted = connect_database(
            str(destination), key=key, encryption_required=True
        )
        destination_schema = _schema(encrypted)
        destination_counts = _table_counts(encrypted)
        destination_integrity = encrypted.execute(
            "PRAGMA integrity_check"
        ).fetchone()
        if source_schema != destination_schema or source_counts != destination_counts:
            raise StorageOpenError("Encrypted migration verification failed.")
        if not destination_integrity or destination_integrity[0] != "ok":
            raise StorageOpenError("Encrypted destination integrity check failed.")
    except Exception:
        if encrypted is not None:
            encrypted.close()
        if destination.exists():
            destination.unlink()
        raise
    finally:
        if plaintext is not None:
            plaintext.close()
    if _file_digest(source) != source_digest:
        raise StorageOpenError("Migration changed the plaintext source database.")
    return {
        "source": str(source),
        "destination": str(destination),
        "tables": len(source_counts),
        "records": sum(source_counts.values()),
        "integrity": "ok",
        "source_unchanged": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate SQLite to SQLCipher.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    key = os.getenv("TWIN_DATABASE_KEY")
    if key is None or not key.strip():
        parser.error("TWIN_DATABASE_KEY must be set to a non-empty value.")
    result = migrate_plaintext_database(args.source, args.destination, key=key)
    print(
        f"Migration complete: {result['tables']} tables, "
        f"{result['records']} records, source unchanged."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
