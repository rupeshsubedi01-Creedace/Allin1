"""Tests for the SSRF guard: the server must refuse to fetch internal targets."""

from __future__ import annotations

import ipaddress

import pytest

from backend.app.services import security
from backend.app.services.errors import (
    BlockedURLError,
    FileTooLargeError,
    InvalidURLError,
    classify_exception,
)

BLOCKED_URLS = [
    "http://127.0.0.1:8000/api/health",
    "http://localhost/admin",
    "http://localhost:9999/secret.mp3",
    "http://[::1]/admin",
    "http://0.0.0.0/",
    "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
    "http://metadata.google.internal/computeMetadata/v1/",
    "http://10.0.0.5/",
    "http://172.16.4.4/",
    "http://192.168.1.1/",
    "http://100.64.0.1/",
    "http://router.local/",
    "http://gitlab.internal/",
    "file:///etc/passwd",
    "ftp://example.com/file.mp4",
    "gopher://127.0.0.1:6379/_INFO",
]


@pytest.mark.parametrize("url", BLOCKED_URLS)
def test_internal_targets_are_blocked(url):
    with pytest.raises((BlockedURLError, InvalidURLError)):
        security.assert_url_allowed(url, resolve=False)


def test_public_urls_are_allowed():
    for url in (
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://cdn.example.com/video.mp4",
        "http://vimeo.com/12345",
    ):
        security.assert_url_allowed(url, resolve=False)


def test_private_urls_allowed_when_explicitly_enabled():
    security.assert_url_allowed("http://127.0.0.1:9999/media.mp4", allow_private=True)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.20.0.1",
        "192.168.0.10",
        "169.254.169.254",
        "0.0.0.0",
        "::1",
        "fc00::1",
        "fe80::1",
        "::ffff:127.0.0.1",  # IPv4-mapped IPv6 spelling of loopback
    ],
)
def test_blocked_ip_ranges(address):
    assert security.is_blocked_ip(ipaddress.ip_address(address)) is True


@pytest.mark.parametrize("address", ["8.8.8.8", "1.1.1.1", "2606:4700::1111"])
def test_public_ip_ranges(address):
    assert security.is_blocked_ip(ipaddress.ip_address(address)) is False


def test_hostname_resolving_to_private_ip_is_blocked(monkeypatch):
    def fake_resolve(hostname, port):  # noqa: ARG001
        return [ipaddress.ip_address("192.168.7.7")]

    monkeypatch.setattr(security, "_resolve", fake_resolve)
    with pytest.raises(BlockedURLError):
        security.assert_url_allowed("http://sneaky.example.com/video.mp4")


def test_unresolvable_hostname_reports_network_error():
    from backend.app.services.errors import NetworkError

    with pytest.raises(NetworkError):
        security.assert_url_allowed("http://this-host-does-not-exist-allin1.invalid/x")


# ------------------------------------------------------------------ API level


def test_extract_blocks_internal_url(strict_client):
    response = strict_client.post("/api/extract", json={"url": "http://127.0.0.1:9999/secret.mp3"})
    assert response.status_code == 403
    assert response.json()["error_code"] == "blocked_url"


def test_extract_blocks_cloud_metadata(strict_client):
    response = strict_client.post(
        "/api/extract", json={"url": "http://169.254.169.254/latest/meta-data/"}
    )
    assert response.status_code == 403


def test_download_blocks_internal_url(strict_client):
    response = strict_client.post(
        "/api/download",
        json={
            "url": "http://127.0.0.1:9999/secret.mp3",
            "format_id": "mp3",
            "media_type": "audio",
            "ext": "mp3",
        },
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "blocked_url"


def test_local_media_is_reachable_when_developer_flag_is_set(client, media_server):
    # Proves the guard (not something else) is what blocks the call above.
    response = client.post("/api/extract", json={"url": media_server})
    assert response.status_code == 200


def test_max_filesize_error_is_classified():
    error = classify_exception(Exception("File is larger than max-filesize (2048 > 1024 bytes)"))
    assert isinstance(error, FileTooLargeError)
    assert error.status_code == 413
