"""
Shared pytest fixtures for the backend test suite.
"""
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture()
def isolated_state_db(tmp_path, monkeypatch):
    """
    Point the SQLite-backed storage module at a throwaway file per
    test, so tests never share state with each other or with a real
    backend/state.db on disk.
    """
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test_state.db"))
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)

    import importlib
    import storage
    importlib.reload(storage)

    import main
    importlib.reload(main)
    return main


@pytest.fixture()
def client(isolated_state_db):
    from fastapi.testclient import TestClient
    return TestClient(isolated_state_db.app)


def make_payment(**overrides):
    """Build a PaymentRecord for tests, with sane defaults that can be
    overridden per-test (e.g. failure_reason, attempt_count)."""
    from models import PaymentRecord, FailureReason

    defaults = dict(
        amount=1000,
        customer_email="test@example.com",
        customer_contact="+911234567890",
        original_method="card",
        failure_reason=FailureReason.CARD_DECLINED,
    )
    defaults.update(overrides)
    return PaymentRecord(**defaults)
