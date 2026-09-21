from backend.app.services.platform_detect import detect_platform, is_valid_url


def test_valid_urls():
    assert is_valid_url("https://www.youtube.com/watch?v=abc123")
    assert is_valid_url("http://example.com/video.mp4")


def test_invalid_urls():
    assert not is_valid_url("not a url")
    assert not is_valid_url("ftp://example.com/file")
    assert not is_valid_url("")
    assert not is_valid_url("   ")
    assert not is_valid_url("javascript:alert(1)")


def test_detect_youtube():
    p = detect_platform("https://www.youtube.com/watch?v=abc123")
    assert p.key == "youtube"

    p2 = detect_platform("https://youtu.be/abc123")
    assert p2.key == "youtube"


def test_detect_tiktok():
    assert detect_platform("https://www.tiktok.com/@user/video/123").key == "tiktok"


def test_detect_instagram():
    assert detect_platform("https://www.instagram.com/reel/abc/").key == "instagram"


def test_detect_twitter_x():
    assert detect_platform("https://x.com/user/status/123").key == "twitter"
    assert detect_platform("https://twitter.com/user/status/123").key == "twitter"


def test_detect_facebook():
    assert detect_platform("https://www.facebook.com/watch/?v=123").key == "facebook"


def test_detect_telegram():
    assert detect_platform("https://t.me/somechannel/123").key == "telegram"


def test_detect_generic_fallback():
    assert detect_platform("https://example.com/video.mp4").key == "generic"
