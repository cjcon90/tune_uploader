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
    tune_id = _tune_id(response)
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
    tune_id = _tune_id(_add(client))
    client.post(f"/tune/{tune_id}/rename", data={"title": "The Old Kesh"})
    assert library.get(tune_id)["title"] == "The Old Kesh"
    assert b"Hidden tunes" not in client.get("/").data
    client.post(f"/tune/{tune_id}/archive")
    assert b"The Old Kesh" not in client.get("/").data
    assert b"Hidden tunes" in client.get("/").data
    assert b"The Old Kesh" in client.get("/archived").data
    client.post(f"/tune/{tune_id}/restore")
    assert b"The Old Kesh" in client.get("/").data


def test_replace_recording_and_sheet(client, library):
    tune_id = _tune_id(_add(client))
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
    tune_id = _tune_id(_add(client))
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


def test_stray_key_error_alerts_instead_of_claiming_not_found(client, app, library):
    def broken(*args, **kwargs):
        raise KeyError("result")

    library.list = broken
    response = client.get("/")
    assert response.status_code == 500
    assert app.sent


def test_too_big_upload_explains_the_limit(client, app):
    app.config["MAX_CONTENT_LENGTH"] = 1000
    response = _add(client, recording=b"x" * 5000)
    assert response.status_code == 413
    assert b"too big" in response.data
    assert app.sent == []


def test_wrong_password_is_slowed_down(app, monkeypatch):
    slept = []
    monkeypatch.setattr("app.routes.time.sleep", slept.append)
    app.test_client().post("/login", data={"password": "nope"})
    assert slept and slept[0] >= 1


def test_go_back_never_leaves_the_site(client):
    response = client.post(
        "/add",
        data={
            "title": " ",
            "sheet": (io.BytesIO(XML), "a.xml"),
            "recording": (io.BytesIO(b"m"), "a.m4a"),
        },
        content_type="multipart/form-data",
        headers={"Referer": "https://evil.example/phish"},
    )
    assert b"evil.example" not in response.data


def test_file_pickers_have_no_type_filter(client):
    # iPadOS greys out real audio files when the picker has an accept filter.
    tune_id = _tune_id(_add(client))
    for page in (client.get("/add").data, client.get(f"/tune/{tune_id}").data):
        assert b'type="file"' in page
        assert b"accept=" not in page


def _tune_id(response) -> str:
    return response.headers["Location"].split("?")[0].rsplit("/", 1)[1]


def test_saving_a_tune_confirms_the_stored_title(client):
    page = _add(client, title="three jolly pigeons")
    assert page.headers["Location"].endswith("?done=saved")
    html = client.get(page.headers["Location"]).data.decode()
    assert "Saved as “Three Jolly Pigeons”" in html


def test_every_change_says_what_happened(client):
    tune_id = _tune_id(_add(client))
    checks = [
        (f"/tune/{tune_id}/rename", {"title": "The Old Kesh"}, "Title changed"),
        (
            f"/tune/{tune_id}/recording",
            {"recording": (io.BytesIO(b"new"), "take2.m4a")},
            "New recording uploaded",
        ),
        (
            f"/tune/{tune_id}/sheet",
            {"sheet": (io.BytesIO(XML), "fixed.xml")},
            "New sheet music uploaded",
        ),
        (f"/tune/{tune_id}/archive", {}, "hidden from your list"),
        (f"/tune/{tune_id}/restore", {}, "back in your list"),
    ]
    for url, data, message in checks:
        response = client.post(
            url, data=data, content_type="multipart/form-data", follow_redirects=True
        )
        assert message in response.data.decode(), url


def test_home_page_makes_opening_a_tune_obvious_and_plays_in_place(client):
    tune_id = _tune_id(_add(client))
    html = client.get("/").data.decode()
    assert f'data-href="/tune/{tune_id}"' in html
    assert f'<audio preload="none" src="https://audio.paulinemahon.com/{tune_id}"' in html
    assert 'href="https://audio.paulinemahon.com/' not in html


def test_inner_pages_have_a_way_back(client):
    tune_id = _tune_id(_add(client))
    for url in ("/add", f"/tune/{tune_id}", "/archived"):
        assert "‹ My Tunes" in client.get(url).data.decode(), url


def test_archive_is_called_hiding(client):
    tune_id = _tune_id(_add(client))
    assert "Hide from my list" in client.get(f"/tune/{tune_id}").data.decode()
    assert "Hidden tunes" in client.get("/archived").data.decode()
    assert "Archive" not in client.get(f"/tune/{tune_id}").data.decode()


def test_links_are_shown_in_full(client):
    tune_id = _tune_id(_add(client))
    html = client.get(f"/tune/{tune_id}").data.decode()
    assert 'value="https://audio' not in html
    assert ">https://audio.paulinemahon.com/the-kesh<" in html


def test_add_page_has_no_example_title(client):
    assert "placeholder" not in client.get("/add").data.decode()
