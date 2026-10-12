"""Every change uploads first and writes tunes.json last: a failure never lists a half-made tune."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from app import audio, render
from app.errors import BlankTitle
from app.naming import new_id, slug_fits, slugify, tidy_title, unique_slug

_lock = threading.Lock()


class RedirectTargetMissing(RuntimeError):
    pass


# Not a KeyError, so a stray KeyError elsewhere still reaches the alerting 500 handler.
class TuneNotFound(Exception):
    pass


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_title(title: str) -> str:
    title = tidy_title(title)
    if not title:
        raise BlankTitle
    return title


def _taken(tunes: list[dict]) -> set[str]:
    return {key for t in tunes for key in (t["id"], t["slug"], *t["old_slugs"])}


def _find(tunes: list[dict], tune_id: str) -> dict:
    for tune in tunes:
        if tune["id"] == tune_id:
            return tune
    raise TuneNotFound(tune_id)


class Library:
    def __init__(
        self,
        store,
        redirects,
        audio_host: str,
        render: Callable = render.render,
        to_mp3: Callable = audio.to_mp3,
        after_change: Callable[[str, str], None] = lambda tune_id, slug: None,
    ) -> None:
        self._store = store
        self._redirects = redirects
        self._audio_host = audio_host
        self._render = render
        self._to_mp3 = to_mp3
        self._after_change = after_change

    def qr_url(self, tune_id: str) -> str:
        return f"https://{self._audio_host}/{tune_id}"

    def list(self, archived: bool = False) -> list[dict]:
        tunes = [t for t in self._store.load_tunes() if t["archived"] == archived]
        return sorted(tunes, key=lambda t: t["created"], reverse=True)

    def get(self, tune_id: str) -> dict:
        return _find(self._store.load_tunes(), tune_id)

    def pdf(self, tune_id: str, with_qr: bool) -> bytes:
        return self._store.get_file(tune_id, "sheet-qr.pdf" if with_qr else "sheet.pdf")

    def add(self, title: str, xml: bytes, audio: bytes, audio_suffix: str) -> str:
        title = _clean_title(title)
        render.parse(xml)
        with _lock:
            tunes = self._store.load_tunes()
            taken = _taken(tunes)
            tune_id = self._fresh_id(taken)
            slug = self._fresh_slug(title, taken | {tune_id})
            with TemporaryDirectory() as tmp:
                work = Path(tmp)
                mp3 = self._convert(audio, audio_suffix, work)
                plain, qr = self._render(xml, title, self.qr_url(tune_id), work)
                self._store.put_file(tune_id, "source.xml", xml, "application/xml")
                self._store.put_file(
                    tune_id, f"original{audio_suffix}", audio, "application/octet-stream"
                )
                self._put_pdfs(tune_id, plain, qr)
            self._store.put_audio(tune_id, mp3)
            self._store.put_audio(slug, mp3)
            self._point(tune_id, slug)
            now = _now()
            tunes.append(
                {
                    "id": tune_id,
                    "title": title,
                    "slug": slug,
                    "old_slugs": [],
                    "archived": False,
                    "created": now,
                    "updated": now,
                }
            )
            self._store.save_tunes(tunes)
        self._after_change(tune_id, slug)
        return tune_id

    def rename(self, tune_id: str, title: str) -> None:
        title = _clean_title(title)
        with _lock:
            tunes = self._store.load_tunes()
            tune = _find(tunes, tune_id)
            if title == tune["title"]:
                return
            xml = self._store.get_file(tune_id, "source.xml")
            with TemporaryDirectory() as tmp:
                plain, qr = self._render(xml, title, self.qr_url(tune_id), Path(tmp))
                new_slug = self._rename_slug(tune, title, tunes)
                if new_slug:
                    self._move_slug(tune, new_slug)
                self._put_pdfs(tune_id, plain, qr)
            tune["title"] = title
            tune["updated"] = _now()
            self._store.save_tunes(tunes)
        self._after_change(tune_id, tune["slug"])

    def replace_audio(self, tune_id: str, audio: bytes, audio_suffix: str) -> None:
        with _lock:
            tunes = self._store.load_tunes()
            tune = _find(tunes, tune_id)
            with TemporaryDirectory() as tmp:
                mp3 = self._convert(audio, audio_suffix, Path(tmp))
            self._store.put_file(
                tune_id, f"original{audio_suffix}", audio, "application/octet-stream"
            )
            # After a half-finished rename the QR may already point past tune["slug"].
            live = self._redirects.target(tune_id)
            for key in {tune_id, tune["slug"], live} - {None}:
                self._store.put_audio(key, mp3)
            tune["updated"] = _now()
            self._store.save_tunes(tunes)
        self._after_change(tune_id, tune["slug"])

    def replace_sheet(self, tune_id: str, xml: bytes) -> None:
        render.parse(xml)
        with _lock:
            tunes = self._store.load_tunes()
            tune = _find(tunes, tune_id)
            with TemporaryDirectory() as tmp:
                plain, qr = self._render(xml, tune["title"], self.qr_url(tune_id), Path(tmp))
                self._put_pdfs(tune_id, plain, qr)
            self._store.put_file(tune_id, "source.xml", xml, "application/xml")
            tune["updated"] = _now()
            self._store.save_tunes(tunes)

    def set_archived(self, tune_id: str, archived: bool) -> None:
        with _lock:
            tunes = self._store.load_tunes()
            tune = _find(tunes, tune_id)
            tune["archived"] = archived
            tune["updated"] = _now()
            self._store.save_tunes(tunes)

    def _fresh_id(self, taken: set[str]) -> str:
        # tunes.json can lag reality (a failed change, a restored backup); R2 is the truth.
        taken = set(taken)
        while self._store.audio_exists(tune_id := new_id(taken)):
            taken.add(tune_id)
        return tune_id

    def _fresh_slug(self, title: str, taken: set[str]) -> str:
        taken = set(taken)
        while self._store.audio_exists(slug := unique_slug(title, taken)):
            taken.add(slug)
        return slug

    def _rename_slug(self, tune: dict, title: str, tunes: list[dict]) -> str | None:
        if slug_fits(title, tune["slug"]):
            return None
        base = slugify(title) or "tune"
        if base in tune["old_slugs"]:
            return base
        return self._fresh_slug(title, _taken(tunes))

    def _move_slug(self, tune: dict, new_slug: str) -> None:
        self._store.copy_audio(tune["id"], new_slug)
        reused = new_slug in tune["old_slugs"]
        if reused:
            self._redirects.remove(new_slug)
        old_slugs = [s for s in tune["old_slugs"] if s != new_slug]
        for source in (tune["id"], tune["slug"], *old_slugs):
            self._point(source, new_slug)
        tune["old_slugs"] = [*old_slugs, tune["slug"]]
        tune["slug"] = new_slug

    def _convert(self, audio: bytes, audio_suffix: str, work: Path) -> bytes:
        # No extension: ffmpeg then sniffs the content and won't treat an upload named .m3u8
        # as a playlist that pulls in other files.
        src, dest = work / "upload", work / "audio.mp3"
        src.write_bytes(audio)
        self._to_mp3(src, dest)
        return dest.read_bytes()

    def _put_pdfs(self, tune_id: str, plain: Path, qr: Path) -> None:
        self._store.put_file(tune_id, "sheet.pdf", plain.read_bytes(), "application/pdf")
        self._store.put_file(tune_id, "sheet-qr.pdf", qr.read_bytes(), "application/pdf")

    def _point(self, source: str, target: str) -> None:
        if not self._store.audio_exists(target):
            raise RedirectTargetMissing(f"{source} -> {target}: no audio at target")
        self._redirects.point(source, target)
