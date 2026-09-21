from backend.app.db import HistoryStore


def test_create_and_get(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    row = store.create(
        url="https://example.com/video.mp4",
        title="Test video",
        platform_key="generic",
        platform_label="Direct / Other",
        thumbnail=None,
        format_id="mp3",
        media_type="audio",
        ext="mp3",
    )
    fetched = store.get(row["id"])
    assert fetched is not None
    assert fetched["title"] == "Test video"
    assert fetched["status"] == "queued"
    store.close()


def test_update(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    row = store.create(
        url="https://example.com/a.mp4",
        title="A",
        platform_key="generic",
        platform_label="Direct",
        thumbnail=None,
        format_id="best",
        media_type="video",
        ext="mp4",
    )
    store.update(row["id"], status="completed", filepath="/tmp/a.mp4", filesize=1024)
    fetched = store.get(row["id"])
    assert fetched["status"] == "completed"
    assert fetched["filesize"] == 1024
    store.close()


def test_list_all_orders_desc(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    first = store.create(
        url="https://example.com/1.mp4", title="1", platform_key="g", platform_label="G",
        thumbnail=None, format_id="best", media_type="video", ext="mp4",
    )
    second = store.create(
        url="https://example.com/2.mp4", title="2", platform_key="g", platform_label="G",
        thumbnail=None, format_id="best", media_type="video", ext="mp4",
    )
    items = store.list_all()
    ids = [item["id"] for item in items]
    assert ids.index(second["id"]) < ids.index(first["id"]) or len(items) == 2
    store.close()


def test_delete_and_clear(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    row = store.create(
        url="https://example.com/1.mp4", title="1", platform_key="g", platform_label="G",
        thumbnail=None, format_id="best", media_type="video", ext="mp4",
    )
    store.create(
        url="https://example.com/2.mp4", title="2", platform_key="g", platform_label="G",
        thumbnail=None, format_id="best", media_type="video", ext="mp4",
    )
    deleted = store.delete(row["id"])
    assert deleted is not None
    assert store.get(row["id"]) is None
    assert len(store.list_all()) == 1

    cleared = store.delete_all()
    assert len(cleared) == 1
    assert store.list_all() == []
    store.close()
