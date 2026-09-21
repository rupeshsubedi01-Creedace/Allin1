"""End-to-end test of extract -> download -> progress -> history using a
locally generated media file served over HTTP. No live social platform is
ever contacted, matching the CI requirement of fully offline tests.
"""

from __future__ import annotations

import json


def _parse_sse(body: str) -> list[dict]:
    events = []
    for chunk in body.split("\n\n"):
        chunk = chunk.strip()
        if not chunk or chunk.startswith(":"):
            continue
        if chunk.startswith("data:"):
            events.append(json.loads(chunk[len("data:"):].strip()))
    return events


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_extract_invalid_url_returns_400(client):
    response = client.post("/api/extract", json={"url": "not-a-url"})
    assert response.status_code == 400
    assert response.json()["error_code"] == "invalid_url"


def test_extract_local_media(client, media_server):
    response = client.post("/api/extract", json={"url": media_server})
    assert response.status_code == 200
    data = response.json()
    assert data["title"]
    assert data["platform_key"] == "generic"
    assert any(f["type"] == "audio" and f["format_id"] == "mp3" for f in data["formats"])
    assert len(data["formats"]) >= 1


def test_full_download_flow_video(client, media_server):
    extract_resp = client.post("/api/extract", json={"url": media_server})
    assert extract_resp.status_code == 200
    data = extract_resp.json()
    video_formats = [f for f in data["formats"] if f["type"] == "video"]
    chosen = video_formats[0] if video_formats else data["formats"][0]

    download_resp = client.post(
        "/api/download",
        json={
            "url": data["webpage_url"],
            "format_id": chosen["format_id"],
            "media_type": chosen["type"],
            "ext": chosen["ext"],
            "requires_merge": chosen.get("requires_merge", False),
            "title": data["title"],
            "thumbnail": data.get("thumbnail"),
            "platform_key": data["platform_key"],
            "platform_label": data["platform_label"],
        },
    )
    assert download_resp.status_code == 200
    job_id = download_resp.json()["job_id"]

    events_resp = client.get(f"/api/download/{job_id}/events")
    assert events_resp.status_code == 200
    events = _parse_sse(events_resp.text)
    assert events, "expected at least one SSE event"
    final_status = events[-1]["status"]
    assert final_status == "completed", f"unexpected final status: {events[-1]}"

    file_resp = client.get(f"/api/download/{job_id}/file")
    assert file_resp.status_code == 200
    assert len(file_resp.content) > 0

    history_resp = client.get("/api/history")
    assert history_resp.status_code == 200
    history = history_resp.json()
    assert any(item["id"] == job_id and item["status"] == "completed" for item in history)


def test_full_download_flow_mp3(client, media_server):
    extract_resp = client.post("/api/extract", json={"url": media_server})
    data = extract_resp.json()

    download_resp = client.post(
        "/api/download",
        json={
            "url": data["webpage_url"],
            "format_id": "mp3",
            "media_type": "audio",
            "ext": "mp3",
            "requires_merge": False,
            "title": data["title"],
            "platform_key": data["platform_key"],
            "platform_label": data["platform_label"],
        },
    )
    assert download_resp.status_code == 200
    job_id = download_resp.json()["job_id"]

    events_resp = client.get(f"/api/download/{job_id}/events")
    events = _parse_sse(events_resp.text)
    assert events[-1]["status"] == "completed"

    file_resp = client.get(f"/api/download/{job_id}/file")
    assert file_resp.status_code == 200
    assert file_resp.headers["content-type"] in ("application/octet-stream",)


def test_redownload_and_history_lifecycle(client, media_server):
    extract_resp = client.post("/api/extract", json={"url": media_server})
    data = extract_resp.json()

    download_resp = client.post(
        "/api/download",
        json={
            "url": data["webpage_url"],
            "format_id": "mp3",
            "media_type": "audio",
            "ext": "mp3",
            "requires_merge": False,
            "title": data["title"],
            "platform_key": data["platform_key"],
            "platform_label": data["platform_label"],
        },
    )
    job_id = download_resp.json()["job_id"]
    client.get(f"/api/download/{job_id}/events")  # wait for completion

    redownload_resp = client.post(f"/api/history/{job_id}/redownload")
    assert redownload_resp.status_code == 200
    new_job_id = redownload_resp.json()["job_id"]
    assert new_job_id != job_id
    client.get(f"/api/download/{new_job_id}/events")

    history = client.get("/api/history").json()
    assert len(history) >= 2

    delete_resp = client.delete(f"/api/history/{job_id}")
    assert delete_resp.status_code == 200
    history_after_delete = client.get("/api/history").json()
    assert all(item["id"] != job_id for item in history_after_delete)

    clear_resp = client.delete("/api/history")
    assert clear_resp.status_code == 200
    assert client.get("/api/history").json() == []


def test_cancel_already_finished_job_returns_409(client, media_server):
    extract_resp = client.post("/api/extract", json={"url": media_server})
    data = extract_resp.json()
    download_resp = client.post(
        "/api/download",
        json={
            "url": data["webpage_url"],
            "format_id": "mp3",
            "media_type": "audio",
            "ext": "mp3",
            "requires_merge": False,
            "title": data["title"],
            "platform_key": data["platform_key"],
            "platform_label": data["platform_label"],
        },
    )
    job_id = download_resp.json()["job_id"]
    client.get(f"/api/download/{job_id}/events")  # wait for completion

    cancel_resp = client.post(f"/api/download/{job_id}/cancel")
    assert cancel_resp.status_code == 409


def test_cancel_unknown_job_returns_404(client):
    response = client.post("/api/download/does-not-exist/cancel")
    assert response.status_code == 404


def test_history_item_not_found(client):
    response = client.delete("/api/history/does-not-exist")
    assert response.status_code == 404
