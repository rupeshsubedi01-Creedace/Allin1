from __future__ import annotations

import functools
import http.server
import shutil
import subprocess
import threading

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app


@pytest.fixture(scope="session")
def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory, ffmpeg_available):
    if not ffmpeg_available:
        pytest.skip("ffmpeg is required to generate local test media")
    media_dir = tmp_path_factory.mktemp("media")
    media_path = media_dir / "sample.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=320x240:rate=15",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=44100",
        "-t",
        "2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(media_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return media_path


@pytest.fixture(scope="session")
def media_server(sample_video):
    directory = str(sample_video.parent)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/{sample_video.name}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


@pytest.fixture()
def app_instance(tmp_path, monkeypatch):
    # The offline suite serves its sample media from 127.0.0.1, which the SSRF
    # guard blocks by default (correctly!). Allow private URLs for these tests.
    monkeypatch.setenv("ALLIN1_ALLOW_PRIVATE_URLS", "true")
    monkeypatch.delenv("ALLIN1_API_KEY", raising=False)
    application = create_app(data_dir=tmp_path / "data")
    yield application
    application.state.history_store.close()


@pytest.fixture()
def client(app_instance):
    with TestClient(app_instance) as test_client:
        yield test_client


@pytest.fixture()
def strict_client(tmp_path, monkeypatch):
    """Client whose app keeps the default, hardened URL policy (no private IPs)."""
    monkeypatch.delenv("ALLIN1_ALLOW_PRIVATE_URLS", raising=False)
    monkeypatch.delenv("ALLIN1_API_KEY", raising=False)
    application = create_app(data_dir=tmp_path / "strict-data")
    try:
        with TestClient(application) as test_client:
            yield test_client
    finally:
        application.state.history_store.close()
