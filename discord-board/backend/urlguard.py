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
