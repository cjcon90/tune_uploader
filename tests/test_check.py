import responses

from app import check

QR = "https://audio.paulinemahon.com/k7mq3xpw"
SLUG = "https://audio.paulinemahon.com/the-kesh"


@responses.activate
def test_redirect_to_mp3_is_healthy():
    responses.get(QR, status=302, headers={"Location": SLUG})
    responses.get(SLUG, status=200, content_type="audio/mpeg", body=b"ID3")
    assert check.check_link(QR, SLUG) is None


@responses.activate
def test_missing_audio_is_reported():
    responses.get(QR, status=302, headers={"Location": SLUG})
    responses.get(SLUG, status=404, content_type="text/html")
    assert check.check_link(QR, SLUG).startswith(f"{QR} -> {SLUG}: 404")


@responses.activate
def test_redirect_loop_is_reported():
    responses.get(QR, status=302, headers={"Location": SLUG})
    responses.get(SLUG, status=302, headers={"Location": QR})
    assert "redirect" in check.check_link(QR, SLUG).lower()


def test_check_later_alerts_only_after_all_attempts_fail(monkeypatch):
    results = iter(["broken", None])
    sent = []
    monkeypatch.setattr(check, "check_link", lambda url, expected: next(results))
    monkeypatch.setattr(check.notify, "send", lambda title, message: sent.append(message))
    check._check_with_retries(QR, SLUG, attempts=2, delay=0)
    assert sent == []


def test_check_later_alerts_when_still_broken(monkeypatch):
    sent = []
    monkeypatch.setattr(check, "check_link", lambda url, expected: "broken")
    monkeypatch.setattr(check.notify, "send", lambda title, message: sent.append(message))
    check._check_with_retries(QR, SLUG, attempts=2, delay=0)
    assert sent == ["broken"]


@responses.activate
def test_fallback_copy_without_the_redirect_is_reported():
    # /<id> playing directly means the vanity redirect is missing.
    responses.get(QR, status=200, content_type="audio/mpeg", body=b"ID3")
    assert check.check_link(QR, SLUG) == f"{QR} -> {QR}: expected {SLUG}"


@responses.activate
def test_two_hop_chain_is_reported():
    middle = "https://audio.paulinemahon.com/the-old-kesh"
    responses.get(QR, status=302, headers={"Location": middle})
    responses.get(middle, status=302, headers={"Location": SLUG})
    responses.get(SLUG, status=200, content_type="audio/mpeg", body=b"ID3")
    assert "redirect" in check.check_link(QR, SLUG).lower()
