import io
import re

from tests.conftest import XML


def _add(client, title="The Kesh", sheet=XML, recording=b"m4a"):
    return client.post(
        "/add",
        data={
            "title": title,
            "sheet": (io.BytesIO(sheet), "the-kesh.musicxml"),
            "recording": (io.BytesIO(recording), "The Kesh.m4a"),
        },
        content_type="multipart/form-data",
    )


def test_pages_need_login(app):
    response = app.test_client().get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_wrong_password_is_refused(app):
    c = app.test_client()
    c.post("/login", data={"password": "nope"})
    assert c.get("/").status_code == 302


def test_session_cookie_is_locked_down(app):
    response = app.test_client().post("/login", data={"password": "fiddle"})
    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert app.config["PERMANENT_SESSION_LIFETIME"].days == 180


def test_add_then_see_it_listed(client, library):
    response = _add(client)
    assert response.status_code == 302
    tune_id = response.headers["Location"].rsplit("/", 1)[1]
    assert b"The Kesh" in client.get("/").data
    page = client.get(f"/tune/{tune_id}").data
    assert f"https://audio.paulinemahon.com/{tune_id}".encode() in page
    assert b"https://audio.paulinemahon.com/the-kesh" in page


def test_wrong_sheet_file_shows_friendly_message(client, app):
    response = _add(client, sheet=b"%PDF-1.7")
    assert response.status_code == 400
    assert b"Export it from StaffPad as MusicXML" in response.data
    assert app.sent == []


def test_blank_title_shows_friendly_message(client):
    response = _add(client, title="  ")
    assert response.status_code == 400
    assert b"Please give the tune a title." in response.data


def test_unexpected_failure_alerts_and_says_nothing_saved(client, app, library):
    def boom(*args):
        raise RuntimeError("MuseScore crashed")

    library._render = boom
    response = _add(client)
    assert response.status_code == 500
    assert b"nothing was saved" in response.data
    assert any("MuseScore crashed" in m for m in app.sent)


def test_unknown_tune_is_404_without_alert(client, app):
    assert client.get("/tune/zzzzzzzz").status_code == 404
    assert app.sent == []


def test_rename_archive_restore(client, library):
    tune_id = _add(client).headers["Location"].rsplit("/", 1)[1]
    client.post(f"/tune/{tune_id}/rename", data={"title": "The Old Kesh"})
    assert library.get(tune_id)["title"] == "The Old Kesh"
    client.post(f"/tune/{tune_id}/archive")
    assert b"The Old Kesh" not in client.get("/").data
    assert b"The Old Kesh" in client.get("/archived").data
    client.post(f"/tune/{tune_id}/restore")
    assert b"The Old Kesh" in client.get("/").data


def test_replace_recording_and_sheet(client, library):
    tune_id = _add(client).headers["Location"].rsplit("/", 1)[1]
    client.post(
        f"/tune/{tune_id}/recording",
        data={"recording": (io.BytesIO(b"new"), "take2.wav")},
        content_type="multipart/form-data",
    )
    assert library._store.get_file(tune_id, "original.wav") == b"new"
    new_xml = b'<score-partwise version="4"/>'
    client.post(
        f"/tune/{tune_id}/sheet",
        data={"sheet": (io.BytesIO(new_xml), "fixed.xml")},
        content_type="multipart/form-data",
    )
    assert library._store.get_file(tune_id, "source.xml") == new_xml


def test_pdf_downloads_open_inline_with_tune_name(client):
    tune_id = _add(client).headers["Location"].rsplit("/", 1)[1]
    response = client.get(f"/tune/{tune_id}/sheet-qr.pdf")
    assert response.mimetype == "application/pdf"
    assert response.headers["Content-Disposition"].startswith("inline")
    assert "The Kesh (QR).pdf" in response.headers["Content-Disposition"]


def test_search_filters_by_title(client):
    _add(client, title="The Kesh")
    _add(client, title="Drowsy Maggie")
    page = client.get("/?q=maggie").data
    assert b"Drowsy Maggie" in page
    assert b"The Kesh" not in page


def test_dates_read_naturally(client):
    _add(client)
    page = client.get("/").data.decode()
    assert re.search(r"\b\d{1,2} [A-Z][a-z]{2} \d{4}\b", page)
    assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", page)


def test_add_button_uses_a_plain_plus(client):
    page = client.get("/").data.decode()
    assert "+ Add a tune" in page
    assert "＋" not in page
