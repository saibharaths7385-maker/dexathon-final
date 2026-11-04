"""Encrypted SQLite connection and configuration helpers."""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class StorageError(RuntimeError):
    """Base class for storage configuration and database failures."""


class StorageConfigurationError(StorageError):
    """Raised when encryption configuration is incomplete or invalid."""


class StorageOpenError(StorageError):
    """Raised when a database cannot be opened with the supplied settings."""


SUPPORTED_SQLCIPHER_MAJOR = 4


@dataclass(frozen=True)
class StorageSettings:
    database: str
    encryption_required: bool
    key: str | None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise StorageConfigurationError(f"{name} must be a boolean value.")


def settings_from_env() -> StorageSettings:
    required = _env_bool("TWIN_DATABASE_ENCRYPTION_REQUIRED", True)
    plaintext_test_mode = _env_bool("TWIN_DATABASE_ALLOW_PLAINTEXT_TEST_MODE", False)
    if not required and not plaintext_test_mode:
        raise StorageConfigurationError(
            "Plaintext database mode requires explicit test-mode opt-in."
        )
    key = os.getenv("TWIN_DATABASE_KEY")
    if required and (key is None or not key.strip()):
        raise StorageConfigurationError(
            "TWIN_DATABASE_KEY is required when database encryption is enabled."
        )
    return StorageSettings(
        database=os.getenv("TWIN_DATABASE", "data/twin.sqlite3"),
        encryption_required=required,
        key=key,
    )


def _require_key(key: str | None) -> str:
    if key is None or not key.strip():
        raise StorageConfigurationError(
            "An external database encryption key is required."
        )
    return key


def _quote_pragma_string(value: str) -> str:
    return value.replace("'", "''")


def _load_sqlcipher() -> Any:
    try:
        import sqlcipher3
    except ImportError as error:
        raise StorageConfigurationError(
            "sqlcipher3 is required for encrypted database storage."
        ) from error
    return sqlcipher3


def _validate_cipher_version(connection: Any) -> None:
    try:
        version = connection.execute("PRAGMA cipher_version").fetchone()
    except Exception as error:
        raise StorageOpenError("Unable to determine SQLCipher version.") from error
    value = version[0] if version else None
    try:
        major = int(str(value).split(".", 1)[0])
    except (TypeError, ValueError) as error:
        raise StorageOpenError("Unsupported SQLCipher version.") from error
    if major != SUPPORTED_SQLCIPHER_MAJOR:
        raise StorageOpenError("Unsupported SQLCipher version.")


def _validate_connection(connection: Any) -> None:
    try:
        _validate_cipher_version(connection)
        connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
        result = connection.execute("PRAGMA integrity_check").fetchone()
    except Exception as error:
        raise StorageOpenError("Unable to validate encrypted database.") from error
    if not result or result[0] != "ok":
        raise StorageOpenError("Encrypted database integrity check failed.")


def connect_database(
    database: str,
    *,
    key: str | None = None,
    encryption_required: bool = True,
    timeout: float = 30.0,
) -> Any:
    """Open and validate a database without ever falling back silently."""
    if database != ":memory:":
        Path(database).parent.mkdir(parents=True, exist_ok=True)

    if not encryption_required:
        connection = sqlite3.connect(
            database, check_same_thread=False, timeout=timeout
        )
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    supplied_key = _require_key(key)
    driver = _load_sqlcipher()
    connection = None
    try:
        connection = driver.connect(
            database, check_same_thread=False, timeout=timeout
        )
        connection.execute(
            f"PRAGMA key = '{_quote_pragma_string(supplied_key)}'"
        )
        _validate_connection(connection)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection
    except StorageError:
        if connection is not None:
            connection.close()
        raise
    except Exception as error:
        if connection is not None:
            connection.close()
        raise StorageOpenError(
            "Unable to open encrypted database with the supplied key."
        ) from error


def close_database(connection: Any) -> None:
    """Close a storage connection without masking the original failure."""
    connection.close()
