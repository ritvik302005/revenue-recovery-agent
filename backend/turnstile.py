"""
Cloudflare Turnstile bot check in front of POST /api/session (P5-1 follow-up).

Off unless TURNSTILE_SECRET_KEY is set (local development and tests run
without it). When on, a session token is only issued for a Turnstile token
that Cloudflare's siteverify accepts: single use, valid 5 minutes, and, if
TURNSTILE_HOSTNAMES is set, solved on one of those hostnames.
Docs: https://developers.cloudflare.com/turnstile/get-started/server-side-validation/
"""
import logging
import os
import uuid
from typing import Optional

import requests

logger = logging.getLogger(__name__)

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY")
TURNSTILE_HOSTNAMES = {h.strip() for h in os.environ.get("TURNSTILE_HOSTNAMES", "").split(",") if h.strip()}
TIMEOUT_SECONDS = 5


class TurnstileUnavailable(Exception):
    """Cloudflare couldn't be asked; the caller fails closed."""


def enabled() -> bool:
    return bool(TURNSTILE_SECRET_KEY)


def verify(token: Optional[str], remote_ip: Optional[str] = None) -> bool:
    if not token:
        return False
    data = {"secret": TURNSTILE_SECRET_KEY, "response": token, "idempotency_key": str(uuid.uuid4())}
    if remote_ip:
        data["remoteip"] = remote_ip
    try:
        result = requests.post(VERIFY_URL, data=data, timeout=TIMEOUT_SECONDS).json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("Turnstile siteverify failed: %r", e)
        raise TurnstileUnavailable() from e
    if not result.get("success"):
        logger.info("Turnstile rejected a token: %s", result.get("error-codes"))
        return False
    if TURNSTILE_HOSTNAMES and result.get("hostname") not in TURNSTILE_HOSTNAMES:
        logger.info("Turnstile token solved on an unexpected hostname: %s", result.get("hostname"))
        return False
    return True
