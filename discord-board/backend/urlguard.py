"""Outbound-URL safety guard (SSRF protection).

User-supplied URLs (outbound webhooks, workflow webhook actions, proof-link
checks) are fetched from inside our network. Before any request, the target
host must resolve only to public addresses — loopback, private ranges,
link-local, and cloud-metadata IPs are rejected.

Note: this is a pre-flight check, not a full DNS-rebinding defense; combined
with short timeouts and never returning response bodies to users, it closes
the practical attack surface.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

log = logging.getLogger("guildizer.urlguard")


def _ip_is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_global and not addr.is_multicast


def is_public_url(url: str) -> bool:
    """True only for http(s) URLs whose host resolves exclusively to public IPs."""
    try:
        parsed = urlparse(url or "")
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    host = parsed.hostname
    # IP literal — check directly.
    try:
        ipaddress.ip_address(host)
        return _ip_is_public(host)
    except ValueError:
        pass
    # Hostname — every resolved address must be public.
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    addresses = {info[4][0] for info in infos}
    if not addresses:
        return False
    return all(_ip_is_public(ip) for ip in addresses)


# -- DNS-rebinding-safe fetch ---------------------------------------------------------
# is_public_url() resolves the host once for the check, but the HTTP client would resolve it
# AGAIN when connecting - an attacker's DNS can answer "public" first and "127.0.0.1" second.
# safe_post() resolves once, validates every address, then makes the connection go to exactly
# the address that was validated (TLS still verifies the original hostname). Redirects are
# never followed.
import threading  # noqa: E402

from urllib3.util import connection as _u3conn  # noqa: E402

_pin = threading.local()
_real_create_connection = _u3conn.create_connection


def _pinned_create_connection(address, *args, **kwargs):
    pins = getattr(_pin, "map", None)
    host, port = address[0], address[1]
    if pins and host in pins:
        address = (pins[host], port)
    return _real_create_connection(address, *args, **kwargs)


if _u3conn.create_connection is _real_create_connection:      # install once, idempotent
    _u3conn.create_connection = _pinned_create_connection


def resolve_public(url: str):
    """(host, ip) for a URL whose host resolves ONLY to public addresses, else None."""
    try:
        parsed = urlparse(url or "")
        host = parsed.hostname
        if parsed.scheme not in ("http", "https") or not host:
            return None
        try:
            ipaddress.ip_address(host)
            return (host, host) if _ip_is_public(host) else None
        except ValueError:
            pass
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except (ValueError, socket.gaierror):
        return None
    addrs = [i[4][0] for i in infos]
    if not addrs or not all(_ip_is_public(a) for a in addrs):
        return None
    return host, addrs[0]


def use_proxy() -> bool:
    import os
    return os.environ.get("OUTBOUND_USE_PROXY", "0").strip().lower() in ("1", "true", "yes", "on")


def safe_post(url: str, **kwargs):
    """requests.post to a validated + pinned public address. Raises ValueError for a
    non-public target; otherwise the usual requests exceptions."""
    import requests
    pinned = resolve_public(url)
    if pinned is None:
        raise ValueError("blocked: non-public URL")
    kwargs["allow_redirects"] = False
    _pin.map = {pinned[0]: pinned[1]}
    try:
        # By default HTTP(S)_PROXY is ignored: through a proxy the client connects to the proxy
        # host, so the pinned (validated) address would never be used. A deployment that MUST go
        # through an egress proxy can opt in with OUTBOUND_USE_PROXY=1 - the target is still
        # validated up front, but the proxy then does its own DNS, so run it with its own
        # private-range blocking.
        with requests.Session() as sess:
            sess.trust_env = use_proxy()
            return sess.post(url, **kwargs)
    finally:
        _pin.map = None
