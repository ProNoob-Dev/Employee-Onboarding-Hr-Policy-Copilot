"""Shared fixtures: fresh app per test, no Azure, tmp audit log."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.graph import Copilot
from app.main import create_app


@pytest.fixture(autouse=True)
def no_azure(monkeypatch):
    for var in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT",
                "AZURE_OPENAI_DEPLOYMENT", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def copilot(tmp_path):
    return Copilot(audit_path=tmp_path / "audit.log")


@pytest.fixture
def client(tmp_path):
    # TestClient is the sync in-process transport; httpx 0.28's
    # ASGITransport is async-only, so it cannot be used from sync tests.
    app = create_app(Copilot(audit_path=tmp_path / "audit.log"))
    with TestClient(app) as c:
        yield c
