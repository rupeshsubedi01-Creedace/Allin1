"""Tests for optional API-key authentication (``ALLIN1_API_KEY``)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings, parse_api_key
from backend.app.main import create_app

API_KEY = "test-key-0123456789abcdef"

PROTECTED_CALLS = [
    ("post", "/api/extract", {"json": {"url": "https://example.com/video"}}),
    ("post", "/api/download", {"json": {"url": "https://example.com/video"}}),
    ("get", "/api/download/some-job/events", {}),
    ("post", "/api/download/some-job/cancel", {}),
    ("get", "/api/download/some-job/file", {}),
    ("get", "/api/history", {}),
    ("delete", "/api/history/some-id", {}),
    ("delete", "/api/history", {}),
    ("post", "/api/history/some-id/redownload", {}),
    ("get", "/docs", {}),
    ("get", "/openapi.json", {}),
]


@pytest.fixture()
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLIN1_API_KEY", API_KEY)
    monkeypatch.setenv("ALLIN1_ALLOW_PRIVATE_URLS", "true")
    application = create_app(data_dir=tmp_path / "auth-data")
    try:
        with TestClient(application) as test_client:
            yield test_client
    finally:
        application.state.history_store.close()


def _call(client, method: str, path: str, kwargs: dict, headers: dict | None = None):
    request = getattr(client, method)
    return request(path, headers=headers or {}, **kwargs)


@pytest.mark.parametrize(("method", "path", "kwargs"), PROTECTED_CALLS)
def test_endpoints_require_a_key(auth_client, method, path, kwargs):
    response = _call(auth_client, method, path, kwargs)
    assert response.status_code == 401, f"{method} {path} should require a key"
    assert response.json()["error_code"] == "unauthorized"
    assert response.json()["auth_required"] is True


@pytest.mark.parametrize(("method", "path", "kwargs"), PROTECTED_CALLS)
def test_wrong_key_is_rejected(auth_client, method, path, kwargs):
    response = _call(auth_client, method, path, kwargs, headers={"X-API-Key": "not-the-key"})
    assert response.status_code == 401


def test_health_stays_public_and_announces_auth(auth_client):
    response = auth_client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["auth_required"] is True


def test_static_frontend_stays_public(auth_client):
    # The PWA shell has to load before a key can be entered.
    assert auth_client.get("/").status_code == 200
    assert auth_client.get("/app/js/auth.js").status_code == 200


def test_x_api_key_header_is_accepted(auth_client):
    response = auth_client.get("/api/history", headers={"X-API-Key": API_KEY})
    assert response.status_code == 200
    assert response.json() == []


def test_bearer_header_is_accepted(auth_client):
    response = auth_client.get("/api/history", headers={"Authorization": f"Bearer {API_KEY}"})
    assert response.status_code == 200


def test_query_parameter_is_accepted(auth_client):
    # Needed by EventSource and <a download>, which cannot set headers.
    response = auth_client.get(f"/api/history?key={API_KEY}")
    assert response.status_code == 200


def test_query_parameter_works_for_sse_stream(auth_client, media_server):
    headers = {"X-API-Key": API_KEY}
    extract = auth_client.post("/api/extract", json={"url": media_server}, headers=headers)
    assert extract.status_code == 200
    data = extract.json()
    fmt = data["formats"][0]

    started = auth_client.post(
        "/api/download",
        headers=headers,
        json={
            "url": data["webpage_url"],
            "format_id": fmt["format_id"],
            "media_type": fmt["type"],
            "ext": fmt["ext"],
            "requires_merge": fmt.get("requires_merge", False),
            "title": data["title"],
            "platform_key": data["platform_key"],
            "platform_label": data["platform_label"],
        },
    )
    assert started.status_code == 200
    job_id = started.json()["job_id"]

    # No header, key in the query string only — exactly what the browser does.
    stream = auth_client.get(f"/api/download/{job_id}/events?key={API_KEY}")
    assert stream.status_code == 200
    assert "data:" in stream.text
    assert auth_client.get(f"/api/download/{job_id}/events").status_code == 401


def test_no_key_configured_means_no_auth(client):
    assert client.get("/api/history").status_code == 200
    assert client.get("/api/health").json()["auth_required"] is False


def test_short_keys_are_rejected_at_startup():
    with pytest.raises(ValueError):
        parse_api_key("tooshort")


def test_blank_key_disables_auth():
    assert parse_api_key(None) is None
    assert parse_api_key("   ") is None


def test_auth_required_property(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        downloads_dir=tmp_path,
        db_path=tmp_path / "history.db",
        ffmpeg_path=None,
        api_key="x" * 20,
    )
    assert settings.auth_required is True
    assert Settings(
        data_dir=tmp_path,
        downloads_dir=tmp_path,
        db_path=tmp_path / "history.db",
        ffmpeg_path=None,
    ).auth_required is False
