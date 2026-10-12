import re
import secrets
import unicodedata

from titlecase import titlecase

ID_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"
# Irish small words that stay lowercase mid-title (titlecase only knows English ones).
# "i", "do" and "go" are left out because they clash with English "I", "Do", "Go".
IRISH_SMALL_WORDS = {"na", "ag", "ar", "le", "de", "sa", "agus", "faoi", "ó"}


def new_id(taken: set[str]) -> str:
    while True:
        candidate = "".join(secrets.choice(ID_ALPHABET) for _ in range(8))
        if candidate not in taken:
            return candidate


def slugify(title: str) -> str:
    # Drop apostrophes before folding so "Paddy's" becomes "paddys", not "paddy-s".
    title = re.sub(r"['’]", "", title)
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")


def unique_slug(title: str, taken: set[str]) -> str:
    base = slugify(title) or "tune"
    slug, n = base, 2
    while slug in taken:
        slug = f"{base}-{n}"
        n += 1
    return slug


def slug_fits(title: str, slug: str) -> bool:
    base = slugify(title) or "tune"
    return slug == base or re.fullmatch(rf"{re.escape(base)}-\d+", slug) is not None


def tidy_title(title: str) -> str:
    title = titlecase(
        " ".join(title.split()),
        callback=lambda word, **kwargs: word.lower() if word.lower() in IRISH_SMALL_WORDS else None,
    )
    return title[:1].upper() + title[1:]
