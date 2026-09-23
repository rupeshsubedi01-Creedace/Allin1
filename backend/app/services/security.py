"""URL safety guard (SSRF protection).

Allin1 accepts an arbitrary URL from the caller and makes the *server* fetch
it. On a publicly reachable deployment that turns the API into a proxy for
whatever the server itself can reach: cloud metadata endpoints
(``169.254.169.254``), other containers, ``localhost`` admin panels, internal
services, ``file://``-style tricks, etc.

This module is the single place that decides whether a URL is allowed to be
fetched. It is deliberately conservative: anything that does not resolve to a
publicly routable address is refused with a 403.

Set ``ALLIN1_ALLOW_PRIVATE_URLS=true`` to disable the IP checks. That is only
meant for local development and the offline test-suite (which serves sample
media from 127.0.0.1) — never enable it on a host that other people can reach.

Residual risk: this checks the hostname at request time. A DNS name could in
theory resolve to a public address for the check and a private one moments
later (DNS rebinding). Closing that fully requires pinning the resolved IP at
connect time, which yt-dlp does not expose. The check below still stops every
realistic case, and combined with an API key (``ALLIN1_API_KEY``) it makes the
endpoint unreachable by strangers in the first place.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from .errors import BlockedURLError, InvalidURLError, NetworkError

# Hostnames that are always internal, regardless of what DNS says.
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata",
        "metadata.google.internal",
    }
)

# Suffixes reserved for local/private use (RFC 6761, RFC 8375, and common
# enterprise conventions).
_BLOCKED_SUFFIXES = (
    ".localhost",
    ".local",
    ".localdomain",
    ".internal",
    ".intranet",
    ".lan",
    ".home.arpa",
)

# Extra ranges worth refusing beyond ``ipaddress.is_private``.
# 100.64.0.0/10  carrier-grade NAT
# 192.0.0.0/24   IETF protocol assignments
# 198.18.0.0/15  benchmarking
# 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24  documentation (RFC 5737)
_EXTRA_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(raw)
    for raw in (
        "100.64.0.0/10",
        "192.0.0.0/24",
        "198.18.0.0/15",
        "192.0.2.0/24",
        "198.51.100.0/24",
        "203.0.113.0/24",
    )
)


def _normalise(ip: ipaddress.IPv4Address | ipaddress.IPv6Address):
    """Unwrap IPv4-mapped/6to4/Teredo IPv6 addresses to a comparable address."""
    if isinstance(ip, ipaddress.IPv6Address):
        for attr in ("ipv4_mapped", "sixtofour", "teredo"):
            mapped = getattr(ip, attr, None)
            if mapped is not None:
                # ``teredo`` yields a (server, client) tuple; keep the client.
                candidate = mapped[1] if isinstance(mapped, tuple) else mapped
                return candidate
    return ip


def is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True when ``ip`` points at the local machine or a private network."""
    address = _normalise(ip)
    if (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        return True
    return any(address in network for network in _EXTRA_BLOCKED_NETWORKS)


def _resolve(hostname: str, port: int | None) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise NetworkError(
            f"Could not resolve the hostname '{hostname}'. Check the link and try again."
        ) from exc
    addresses = []
    for info in infos:
        raw = info[4][0]
        try:
            addresses.append(ipaddress.ip_address(raw))
        except ValueError:  # pragma: no cover - getaddrinfo should always be parseable
            continue
    return addresses


def assert_url_allowed(url: str, *, allow_private: bool = False, resolve: bool = True) -> None:
    """Validate ``url`` and raise an ``AppError`` if it must not be fetched.

    ``resolve=False`` skips the DNS lookup (used by unit tests and by callers
    that only need the syntactic checks).
    """
    try:
        parsed = urlsplit(url.strip())
    except ValueError as exc:
        raise InvalidURLError() from exc

    if parsed.scheme not in ("http", "https"):
        raise BlockedURLError("Only http:// and https:// links can be fetched.")

    hostname = parsed.hostname
    if not hostname:
        raise InvalidURLError()

    if allow_private:
        return

    host = hostname.rstrip(".").lower()

    if host in _BLOCKED_HOSTNAMES or host.endswith(_BLOCKED_SUFFIXES):
        raise BlockedURLError(
            "This link points at a local or internal address, which Allin1 refuses to fetch."
        )

    # Literal IP address (including bracketed IPv6): no DNS involved.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    if literal is not None:
        if is_blocked_ip(literal):
            raise BlockedURLError(
                "This link points at a private, loopback or internal address, "
                "which Allin1 refuses to fetch."
            )
        return

    if not resolve:
        return

    try:
        port = parsed.port
    except ValueError as exc:
        raise InvalidURLError() from exc

    for address in _resolve(host, port):
        if is_blocked_ip(address):
            raise BlockedURLError(
                f"'{host}' resolves to an internal address ({address}), "
                "which Allin1 refuses to fetch."
            )
