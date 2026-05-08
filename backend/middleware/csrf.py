"""CSRF double-submit cookie protection (1-D-02)."""
import hmac
import secrets
from flask import request, abort


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def validate_csrf():
    """Call in before_request for all state-changing endpoints."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    cookie_token = request.cookies.get("csrf_token")
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token:
        abort(403, "CSRF token missing")
    if not hmac.compare_digest(cookie_token, header_token):
        abort(403, "CSRF token invalid")
