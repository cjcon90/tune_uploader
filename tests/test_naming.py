import pytest

from app.naming import ID_ALPHABET, new_id, slugify, tidy_title, unique_slug


def test_new_id_is_8_unambiguous_chars():
    tune_id = new_id(set())
    assert len(tune_id) == 8
    assert set(tune_id) <= set(ID_ALPHABET)
    assert not set("01ilo") & set(ID_ALPHABET)


def test_new_id_avoids_taken(monkeypatch):
    picks = iter("aaaaaaaa" + "bbbbbbbb")
    monkeypatch.setattr("app.naming.secrets.choice", lambda _: next(picks))
    assert new_id({"aaaaaaaa"}) == "bbbbbbbb"


@pytest.mark.parametrize(
    ("title", "slug"),
    [
        ("A Pint for Ciaran.", "a-pint-for-ciaran"),
        ("Ríl Uí Néill", "ril-ui-neill"),
        ("Paddy's Return", "paddys-return"),
        ("Paddy’s Return", "paddys-return"),
        ("  The   Kesh -- Jig ", "the-kesh-jig"),
        ("🎻", ""),
    ],
)
def test_slugify(title, slug):
    assert slugify(title) == slug


def test_unique_slug_numbers_clashes():
    assert unique_slug("The Kesh", {"the-kesh", "the-kesh-2"}) == "the-kesh-3"


def test_unique_slug_falls_back_when_title_has_no_letters():
    assert unique_slug("🎻", set()) == "tune"
    assert unique_slug("🎻", {"tune"}) == "tune-2"


def test_unique_slug_never_equals_an_id():
    # An 8-letter one-word title could otherwise land on an existing ID key.
    assert unique_slug("kesh2jig", {"kesh2jig"}) == "kesh2jig-2"


@pytest.mark.parametrize(
    ("typed", "tidy"),
    [
        ("three jolly pigeons", "Three Jolly Pigeons"),
        ("a pint for ciaran.", "A Pint for Ciaran."),
        ("THREE JOLLY PIGEONS", "Three Jolly Pigeons"),
        ("jig for john mcdermott", "Jig for John McDermott"),
        ("o'neill's march", "O'Neill's March"),
        ("ríl uí néill", "Ríl Uí Néill"),
        ("port na bPúcaí", "Port na bPúcaí"),
        ("an raibh tú ag an gCarraig", "An Raibh Tú ag an gCarraig"),
        ("na píobairí", "Na Píobairí"),
        ("  out  on the   ocean ", "Out on the Ocean"),
    ],
)
def test_tidy_title(typed, tidy):
    assert tidy_title(typed) == tidy
