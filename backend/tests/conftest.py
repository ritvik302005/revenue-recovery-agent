"""
Shared pytest fixtures for the backend test suite.
"""
import hashlib
import hmac
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# A fixed key secret for signature checks, so tests never depend on the
# real backend/.env.
TEST_KEY_SECRET = "test_secret_for_signature_checks"


@pytest.fixture(autouse=True)
def fixed_signing_secret(monkeypatch):
    import razorpay_client
    monkeypatch.setattr(razorpay_client, "RAZORPAY_KEY_SECRET", TEST_KEY_SECRET)


def sign(order_id: str, payment_id: str) -> str:
    """The razorpay_signature Checkout would return for this order and
    payment, computed independently of the SDK."""
    return hmac.new(TEST_KEY_SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


@pytest.fixture()
def isolated_state_db(tmp_path, monkeypatch):
    """
    Point the SQLite-backed storage module at a throwaway file per
    test, so tests never share state with each other or with a real
    backend/state.db on disk.
    """
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test_state.db"))
    monkeypatch.delenv("REDIS_URL", raising=False)

    import importlib
    import storage
    importlib.reload(storage)

    import main
    importlib.reload(main)
    return main


@pytest.fixture()
def anon_client(isolated_state_db):
    """A client with no session token."""
    from fastapi.testclient import TestClient
    return TestClient(isolated_state_db.app)


def new_session_client(main_module):
    """A client holding its own session token, as the frontend would."""
    from fastapi.testclient import TestClient
    c = TestClient(main_module.app)
    c.headers["X-Session-Token"] = c.post("/api/session").json()["token"]
    return c


def owner(client) -> str:
    """The owner id a live-demo record created by this client would carry."""
    import access
    return access.owner_of(client.headers["X-Session-Token"])


@pytest.fixture()
def client(isolated_state_db):
    return new_session_client(isolated_state_db)


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
