import os

import pytest


@pytest.fixture(autouse=True)
def legacy_storage_mode(monkeypatch):
    """Explicitly opt legacy API tests into isolated plaintext test mode."""
    if "TWIN_DATABASE_ENCRYPTION_REQUIRED" not in os.environ:
        monkeypatch.setenv("TWIN_DATABASE_ENCRYPTION_REQUIRED", "false")
        monkeypatch.setenv("TWIN_DATABASE_ALLOW_PLAINTEXT_TEST_MODE", "true")
