import boto3
import pytest
from moto import mock_aws

from app.audio import to_mp3
from app.errors import BlankTitle, NotAudio, NotMusicXML
from app.library import Library, RedirectTargetMissing, TuneNotFound
from app.store import Store
from tests.fakes import FakeRedirects, fake_render, fake_to_mp3

XML = b"<score-partwise/>"
NEW_XML = b'<score-partwise version="4"/>'


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="pm-tunes")
        client.create_bucket(Bucket="pm-audio")
        yield client


@pytest.fixture
def redirects():
    return FakeRedirects()


@pytest.fixture
def changed():
    return []


@pytest.fixture
def library(s3, redirects, changed):
    return Library(
        Store(s3, "pm-tunes", "pm-audio"),
        redirects,
        "audio.paulinemahon.com",
        render=fake_render,
        to_mp3=fake_to_mp3,
        after_change=lambda tune_id, slug: changed.append((tune_id, slug)),
    )


def _audio(s3, key):
    return s3.get_object(Bucket="pm-audio", Key=key)["Body"].read()


def _assert_no_loops_or_chains(table):
    for source, target in table.items():
        assert source != target
        assert target not in table


def test_add_publishes_audio_under_id_and_slug_then_lists_it(library, s3, redirects, changed):
    tune_id = library.add("The Kesh", XML, b"m4a", ".m4a")
    assert _audio(s3, tune_id) == b"MP3 m4a"
    assert _audio(s3, "the-kesh") == b"MP3 m4a"
    assert redirects.table == {tune_id: "the-kesh"}
    assert library.pdf(tune_id, with_qr=True) == (
        f"PDF The Kesh https://audio.paulinemahon.com/{tune_id}".encode()
    )
    assert library.get(tune_id)["slug"] == "the-kesh"
    assert changed == [(tune_id, "the-kesh")]


def test_add_rejects_blank_title_before_doing_anything(library, s3):
    with pytest.raises(BlankTitle):
        library.add("   ", XML, b"m4a", ".m4a")
    assert s3.list_objects_v2(Bucket="pm-audio").get("KeyCount") == 0


def test_wrong_file_is_refused_before_any_work(library, s3):
    with pytest.raises(NotMusicXML):
        library.add("The Kesh", b"%PDF-1.7", b"m4a", ".m4a")
    assert s3.list_objects_v2(Bucket="pm-tunes").get("KeyCount") == 0


def test_failed_render_leaves_no_tune_listed(library, s3):
    def broken_render(*args):
        raise NotMusicXML

    library._render = broken_render
    with pytest.raises(NotMusicXML):
        library.add("The Kesh", XML, b"m4a", ".m4a")
    assert library.list() == []


def test_failed_redirect_leaves_no_tune_listed(library, redirects):
    def broken_point(source, target):
        raise RuntimeError("cloudflare down")

    redirects.point = broken_point
    with pytest.raises(RuntimeError):
        library.add("The Kesh", XML, b"m4a", ".m4a")
    assert library.list() == []


def test_redirect_is_refused_when_target_audio_is_missing(library, s3):
    library._store.put_audio = lambda key, data: None
    with pytest.raises(RedirectTargetMissing):
        library.add("The Kesh", XML, b"m4a", ".m4a")
    assert library.list() == []


def test_same_title_twice_gives_two_working_tunes(library, s3, redirects):
    first = library.add("The Kesh", XML, b"one", ".m4a")
    second = library.add("The Kesh", XML, b"two", ".m4a")
    assert first != second
    assert redirects.table == {first: "the-kesh", second: "the-kesh-2"}
    assert _audio(s3, "the-kesh-2") == b"MP3 two"
    assert len(library.list()) == 2


def test_rename_moves_vanity_url_and_keeps_qr(library, s3, redirects):
    tune_id = library.add("The Kesh", XML, b"m4a", ".m4a")
    library.rename(tune_id, "The Kesh Jig")
    library.rename(tune_id, "The Old Kesh")
    tune = library.get(tune_id)
    assert tune["slug"] == "the-old-kesh"
    assert tune["old_slugs"] == ["the-kesh", "the-kesh-jig"]
    assert redirects.table == {
        tune_id: "the-old-kesh",
        "the-kesh": "the-old-kesh",
        "the-kesh-jig": "the-old-kesh",
    }
    _assert_no_loops_or_chains(redirects.table)
    assert _audio(s3, "the-old-kesh") == b"MP3 m4a"
    assert library.pdf(tune_id, with_qr=True) == (
        f"PDF The Old Kesh https://audio.paulinemahon.com/{tune_id}".encode()
    )


def test_rename_back_to_an_old_name_never_loops(library, redirects):
    tune_id = library.add("The Kesh", XML, b"m4a", ".m4a")
    library.rename(tune_id, "The Kesh Jig")
    library.rename(tune_id, "The Kesh")
    assert library.get(tune_id)["slug"] == "the-kesh"
    _assert_no_loops_or_chains(redirects.table)


def test_rename_that_only_changes_punctuation_keeps_slug(library, redirects):
    tune_id = library.add("A Pint for Ciaran.", XML, b"m4a", ".m4a")
    redirects.calls.clear()
    library.rename(tune_id, "A Pint for Ciaran")
    assert library.get(tune_id)["slug"] == "a-pint-for-ciaran"
    assert library.get(tune_id)["title"] == "A Pint for Ciaran"
    assert redirects.calls == []
    assert library.pdf(tune_id, with_qr=False) == b"PDF A Pint for Ciaran"


def test_replace_audio_updates_id_and_current_slug(library, s3):
    tune_id = library.add("The Kesh", XML, b"old", ".m4a")
    library.replace_audio(tune_id, b"new", ".wav")
    assert _audio(s3, tune_id) == b"MP3 new"
    assert _audio(s3, "the-kesh") == b"MP3 new"
    assert library._store.get_file(tune_id, "original.wav") == b"new"


def test_replace_sheet_rerenders_with_current_title(library):
    tune_id = library.add("The Kesh", XML, b"m4a", ".m4a")
    library.replace_sheet(tune_id, NEW_XML)
    assert library._store.get_file(tune_id, "source.xml") == NEW_XML
    assert library.pdf(tune_id, with_qr=False) == b"PDF The Kesh"


def test_archive_hides_but_keeps_everything(library, s3, redirects):
    tune_id = library.add("The Kesh", XML, b"m4a", ".m4a")
    library.set_archived(tune_id, True)
    assert library.list() == []
    assert [t["id"] for t in library.list(archived=True)] == [tune_id]
    assert _audio(s3, tune_id) == b"MP3 m4a"
    assert redirects.table == {tune_id: "the-kesh"}
    library.set_archived(tune_id, False)
    assert [t["id"] for t in library.list()] == [tune_id]


def test_unknown_tune_raises_tune_not_found(library):
    with pytest.raises(TuneNotFound):
        library.get("zzzzzzzz")


def test_new_slug_never_reuses_a_key_that_already_has_audio(library, s3):
    # e.g. left behind by a rename that failed halfway, or a lost tunes.json
    library._store.put_audio("the-kesh", b"someone else's tune")
    tune_id = library.add("The Kesh", XML, b"m4a", ".m4a")
    assert library.get(tune_id)["slug"] == "the-kesh-2"
    assert _audio(s3, "the-kesh") == b"someone else's tune"


def test_new_id_never_reuses_a_key_that_already_has_audio(library, monkeypatch):
    library._store.put_audio("aaaaaaaa", b"orphan")
    ids = iter(["aaaaaaaa", "bbbbbbbb"])
    monkeypatch.setattr("app.library.new_id", lambda taken: next(i for i in ids if i not in taken))
    assert library.add("The Kesh", XML, b"m4a", ".m4a") == "bbbbbbbb"


def test_failed_rename_cannot_hand_its_new_slug_to_another_tune(library, s3, redirects):
    alpha = library.add("Alpha", XML, b"alpha", ".m4a")
    real_point = redirects.point

    def fail_on_old_slug(source, target):
        if source == "alpha":
            raise RuntimeError("cloudflare 500")
        real_point(source, target)

    redirects.point = fail_on_old_slug
    with pytest.raises(RuntimeError):
        library.rename(alpha, "Beta")
    redirects.point = real_point
    library.add("Beta", XML, b"beta", ".m4a")
    assert _audio(s3, redirects.table[alpha]) == b"MP3 alpha"


def test_punctuation_rename_keeps_a_numbered_slug(library, redirects):
    library.add("Reel", XML, b"m4a", ".m4a")
    second = library.add("Reel", XML, b"m4a", ".m4a")
    redirects.calls.clear()
    library.rename(second, "Reel!")
    assert library.get(second)["slug"] == "reel-2"
    assert redirects.calls == []


def test_rename_back_to_an_old_name_reuses_its_slug(library, s3, redirects):
    tune_id = library.add("The Kesh", XML, b"m4a", ".m4a")
    library.rename(tune_id, "The Kesh Jig")
    library.rename(tune_id, "The Kesh")
    tune = library.get(tune_id)
    assert tune["slug"] == "the-kesh"
    assert tune["old_slugs"] == ["the-kesh-jig"]
    assert redirects.table == {tune_id: "the-kesh", "the-kesh-jig": "the-kesh"}
    _assert_no_loops_or_chains(redirects.table)
    assert _audio(s3, "the-kesh") == b"MP3 m4a"


def test_failed_rename_leaves_the_pdfs_alone(library, redirects):
    tune_id = library.add("The Kesh", XML, b"m4a", ".m4a")

    def broken_point(source, target):
        raise RuntimeError("cloudflare down")

    redirects.point = broken_point
    with pytest.raises(RuntimeError):
        library.rename(tune_id, "The Kesh Jig")
    assert library.pdf(tune_id, with_qr=False) == b"PDF The Kesh"
    assert library.get(tune_id)["title"] == "The Kesh"


def test_replace_audio_follows_where_the_qr_really_points(library, s3, redirects):
    tune_id = library.add("The Kesh", XML, b"old", ".m4a")
    library._store.put_audio("half-done", b"MP3 old")
    redirects.table[tune_id] = "half-done"
    library.replace_audio(tune_id, b"new", ".m4a")
    assert _audio(s3, "half-done") == b"MP3 new"


def test_uploaded_playlist_cannot_pull_in_local_files(s3, redirects, tmp_path):
    import subprocess

    secret = tmp_path / "secret.ts"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=1", str(secret)], check=True
    )
    playlist = f"#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:1,\nfile://{secret}\n#EXT-X-ENDLIST\n"
    library = Library(
        Store(s3, "pm-tunes", "pm-audio"),
        redirects,
        "audio.paulinemahon.com",
        render=fake_render,
        to_mp3=to_mp3,
    )
    with pytest.raises(NotAudio):
        library.add("The Kesh", XML, playlist.encode(), ".m3u8")
