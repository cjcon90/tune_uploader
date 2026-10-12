import re
import secrets
import unicodedata

ID_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"


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
