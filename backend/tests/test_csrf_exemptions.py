"""CSRF double-submit must cover cookie-authenticated routes; only inbound webhooks are exempt.

Regression: '/api/telegram/' and '/api/integrations/' were exempt as whole prefixes, which silently
skipped CSRF for /api/telegram/disconnect, /api/telegram/generate-connect-code and
/api/integrations/webhooks* (all cookie-authenticated, state-changing).

Run from the repo root:  python -m pytest backend/tests/test_csrf_exemptions.py
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-with-enough-length-1234")
os.environ.setdefault("ENCRYPTION_KEY", "Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmE=")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

from backend.app import create_app


@pytest.fixture(scope="module")
def app():
    return create_app()


def _client(app, csrf_cookie="a"):
    c = app.test_client()
    c.set_cookie("access_token", "not-a-real-token")
    if csrf_cookie:
        c.set_cookie("csrf_token", csrf_cookie)
    return c


@pytest.mark.parametrize("method,path", [
    ("DELETE", "/api/telegram/disconnect"),
    ("POST", "/api/telegram/generate-connect-code"),
    ("POST", "/api/integrations/webhooks"),
    ("PUT", "/api/integrations/webhooks/1"),
    ("DELETE", "/api/integrations/webhooks/1"),
    ("POST", "/api/integrations/webhooks/1/test"),
])
def test_cookie_authed_mutations_require_csrf(app, method, path):
    r = _client(app).open(path, method=method)  # cookies present, no X-CSRF-Token header
    assert r.status_code == 403 and r.get_json()["code"] == "CSRF_FAILED"
    r = _client(app).open(path, method=method, headers={"X-CSRF-Token": "different"})
    assert r.status_code == 403 and r.get_json()["code"] == "CSRF_FAILED"


def test_matching_csrf_token_gets_past_the_csrf_gate(app):
    r = _client(app).open("/api/telegram/disconnect", method="DELETE", headers={"X-CSRF-Token": "a"})
    # rejected later (bad JWT), but NOT by the CSRF gate
    assert (r.get_json(silent=True) or {}).get("code") != "CSRF_FAILED"


@pytest.mark.parametrize("path", [
    "/api/telegram/custom/5",       # custom-bot webhook receiver (Telegram posts here, no cookies)
    "/api/tg-update/abc",           # per-bot webhook receiver
    "/api/official-bot-update",
])
def test_inbound_webhook_receivers_stay_exempt(app, path):
    r = _client(app).post(path)
    assert (r.get_json(silent=True) or {}).get("code") != "CSRF_FAILED"
