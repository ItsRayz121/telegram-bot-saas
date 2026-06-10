"""Minimal NOWPayments client for Guildizer (separate webhook from Telegizer).

Two responsibilities:
  - create_invoice(): hosted-checkout invoice → returns (invoice_url, invoice_id)
  - verify_ipn(): validate the x-nowpayments-sig HMAC-SHA512 over the sorted JSON
    body (same scheme Telegizer uses), so we only act on authentic callbacks.
"""
from __future__ import annotations

import hashlib
import hmac
import json

import requests

from config import Config

_API = "https://api.nowpayments.io/v1"
_TIMEOUT = 20

# Payment statuses NOWPayments reports as fully paid.
PAID_STATUSES = ("finished", "confirmed")


def is_configured() -> bool:
    return bool(Config.NOWPAYMENTS_API_KEY)


def create_invoice(*, order_id: str, amount: float, currency: str,
                   ipn_url: str, success_url: str, cancel_url: str) -> dict:
    """Create a hosted invoice. Raises requests.HTTPError on failure."""
    payload = {
        "price_amount": amount,
        "price_currency": currency,
        "order_id": order_id,
        "order_description": "Guildizer Pro",
        "ipn_callback_url": ipn_url,
        "success_url": success_url,
        "cancel_url": cancel_url,
    }
    resp = requests.post(
        f"{_API}/invoice",
        json=payload,
        headers={"x-api-key": Config.NOWPAYMENTS_API_KEY, "Content-Type": "application/json"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def verify_ipn(raw_body: bytes, signature: str) -> bool:
    """True if the IPN signature matches our IPN secret over the sorted body."""
    secret = Config.NOWPAYMENTS_IPN_SECRET
    if not secret or not signature:
        return False
    try:
        body = json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return False
    sorted_body = json.dumps(body, sort_keys=True, separators=(",", ":"))
    expected = hmac.new(secret.encode(), sorted_body.encode(), hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)
