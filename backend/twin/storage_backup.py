"""Encrypted SQLCipher backup and restore utilities."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from .storage import StorageOpenError, connect_database


def _verified_backup(
    source: Any,
    destination_path: str,
    *,
    key: str,
) -> dict[str, object]:
    destination = Path(destination_path)
    if destination.exists():
        raise FileExistsError("Backup destination already exists.")
    target = None
    try:
        target = connect_database(str(destination), key=key, encryption_required=True)
        source.backup(target)
        target.commit()
        integrity = target.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise StorageOpenError("Encrypted backup integrity check failed.")
    except Exception:
        if destination.exists():
            destination.unlink()
        raise
    finally:
        if target is not None:
            target.close()
    return {"path": str(destination), "integrity": "ok"}


def backup_database(
    source_path: str,
    destination_path: str,
    *,
    key: str,
) -> dict[str, object]:
    """Create an encrypted backup through the SQLite backup API."""
    source = connect_database(source_path, key=key, encryption_required=True)
    try:
        return _verified_backup(source, destination_path, key=key)
    finally:
        source.close()


def restore_database(
    backup_path: str,
    destination_path: str,
    *,
    key: str,
) -> dict[str, object]:
    """Restore an encrypted backup into a new destination only."""
    backup = connect_database(backup_path, key=key, encryption_required=True)
    try:
        result = _verified_backup(backup, destination_path, key=key)
        result["restored_from"] = str(Path(backup_path))
        return result
    finally:
        backup.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage encrypted SQLCipher backups.")
    parser.add_argument("action", choices=("backup", "restore"))
    parser.add_argument("--source", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    key = os.getenv("TWIN_DATABASE_KEY")
    if not key:
        raise SystemExit("TWIN_DATABASE_KEY is required.")
    operation = backup_database if args.action == "backup" else restore_database
    result = operation(args.source, args.destination, key=key)
    print(f"{args.action.title()} complete: integrity={result['integrity']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
