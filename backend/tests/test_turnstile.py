"""
Turnstile in front of POST /api/session: off without a secret; when on,
only a token Cloudflare accepts gets a session, and an unreachable
Cloudflare fails closed. Cloudflare is mocked; nothing hits the network.
"""
from unittest.mock import MagicMock, patch

import pytest
import requests

import turnstile


def _cloudflare(result=None, error=None):
    def post(url, data, timeout):
        assert url == turnstile.VERIFY_URL and data["secret"] == "test-secret" and timeout == turnstile.TIMEOUT_SECONDS
        if error:
            raise error
        response = MagicMock()
        response.json.return_value = result
        return response
    return patch("turnstile.requests.post", side_effect=post)


@pytest.fixture()
def turnstile_on(monkeypatch):
    monkeypatch.setattr(turnstile, "TURNSTILE_SECRET_KEY", "test-secret")
    monkeypatch.setattr(turnstile, "TURNSTILE_HOSTNAMES", set())


def test_off_without_a_secret(anon_client):
    assert not turnstile.enabled()
    with patch("turnstile.requests.post") as post:
        assert anon_client.post("/api/session").status_code == 200
    post.assert_not_called()


def test_valid_token_gets_a_session(anon_client, turnstile_on):
    with _cloudflare({"success": True, "hostname": "localhost"}) as post:
        r = anon_client.post("/api/session", json={"turnstile_token": "tok"})
    assert r.status_code == 200 and r.json()["token"]
    assert post.call_args.kwargs["data"]["response"] == "tok"
    assert post.call_args.kwargs["data"]["remoteip"] == "testclient"


@pytest.mark.parametrize("body", [None, {}, {"turnstile_token": ""}])
def test_missing_token_is_refused_without_asking_cloudflare(anon_client, turnstile_on, body):
    with patch("turnstile.requests.post") as post:
        r = anon_client.post("/api/session", json=body) if body is not None else anon_client.post("/api/session")
    assert r.status_code == 403
    post.assert_not_called()


def test_rejected_token_is_refused(anon_client, turnstile_on):
    with _cloudflare({"success": False, "error-codes": ["timeout-or-duplicate"]}):
        r = anon_client.post("/api/session", json={"turnstile_token": "used"})
    assert r.status_code == 403
    assert "human" in r.json()["detail"]


def test_wrong_hostname_is_refused(anon_client, turnstile_on, monkeypatch):
    monkeypatch.setattr(turnstile, "TURNSTILE_HOSTNAMES", {"revenue-recovery-agent.vercel.app"})
    with _cloudflare({"success": True, "hostname": "evil.example"}):
        assert anon_client.post("/api/session", json={"turnstile_token": "tok"}).status_code == 403
    with _cloudflare({"success": True, "hostname": "revenue-recovery-agent.vercel.app"}):
        assert anon_client.post("/api/session", json={"turnstile_token": "tok"}).status_code == 200


def test_cloudflare_unreachable_fails_closed(anon_client, turnstile_on):
    with _cloudflare(error=requests.ConnectionError("down")):
        r = anon_client.post("/api/session", json={"turnstile_token": "tok"})
    assert r.status_code == 503


def test_overlong_token_is_rejected(anon_client, turnstile_on):
    assert anon_client.post("/api/session", json={"turnstile_token": "x" * 2049}).status_code == 422
