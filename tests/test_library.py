import boto3
import pytest
from moto import mock_aws

from app.errors import BlankTitle, NotMusicXML
from app.library import Library, RedirectTargetMissing
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
        after_change=changed.append,
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
    assert changed == [tune_id]


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
    assert library.get(tune_id)["slug"] == "the-kesh-2"
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


def test_unknown_tune_raises_key_error(library):
    with pytest.raises(KeyError):
        library.get("zzzzzzzz")
