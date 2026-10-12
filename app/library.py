"""Every change uploads first and writes tunes.json last: a failure never lists a half-made tune."""

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from app import audio, render
from app.errors import BlankTitle
from app.naming import new_id, slugify, unique_slug

_lock = threading.Lock()


class RedirectTargetMissing(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_title(title: str) -> str:
    title = " ".join(title.split())
    if not title:
        raise BlankTitle
    return title


def _taken(tunes: list[dict]) -> set[str]:
    return {key for t in tunes for key in (t["id"], t["slug"], *t["old_slugs"])}


def _find(tunes: list[dict], tune_id: str) -> dict:
    for tune in tunes:
        if tune["id"] == tune_id:
            return tune
    raise KeyError(tune_id)


class Library:
    def __init__(
        self,
        store,
        redirects,
        audio_host: str,
        render: Callable = render.render,
        to_mp3: Callable = audio.to_mp3,
        after_change: Callable[[str], None] = lambda tune_id: None,
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
            tune_id = new_id(taken)
            slug = unique_slug(title, taken | {tune_id})
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
        self._after_change(tune_id)
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
                self._put_pdfs(tune_id, plain, qr)
            if slugify(title) != tune["slug"]:
                new_slug = unique_slug(title, _taken(tunes))
                self._store.copy_audio(tune_id, new_slug)
                for source in (tune_id, tune["slug"], *tune["old_slugs"]):
                    self._point(source, new_slug)
                tune["old_slugs"].append(tune["slug"])
                tune["slug"] = new_slug
            tune["title"] = title
            tune["updated"] = _now()
            self._store.save_tunes(tunes)
        self._after_change(tune_id)

    def replace_audio(self, tune_id: str, audio: bytes, audio_suffix: str) -> None:
        with _lock:
            tunes = self._store.load_tunes()
            tune = _find(tunes, tune_id)
            with TemporaryDirectory() as tmp:
                mp3 = self._convert(audio, audio_suffix, Path(tmp))
            self._store.put_file(
                tune_id, f"original{audio_suffix}", audio, "application/octet-stream"
            )
            self._store.put_audio(tune_id, mp3)
            self._store.put_audio(tune["slug"], mp3)
            tune["updated"] = _now()
            self._store.save_tunes(tunes)
        self._after_change(tune_id)

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

    def _convert(self, audio: bytes, audio_suffix: str, work: Path) -> bytes:
        src, dest = work / f"upload{audio_suffix}", work / "audio.mp3"
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
