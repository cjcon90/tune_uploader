from pathlib import Path


class FakeRedirects:
    def __init__(self) -> None:
        self.table: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []

    def point(self, source: str, target: str) -> None:
        self.calls.append((source, target))
        self.table[source] = target


def fake_render(xml: bytes, title: str, qr_url: str, work_dir: Path) -> tuple[Path, Path]:
    plain, qr = work_dir / "sheet.pdf", work_dir / "sheet-qr.pdf"
    plain.write_bytes(f"PDF {title}".encode())
    qr.write_bytes(f"PDF {title} {qr_url}".encode())
    return plain, qr


def fake_to_mp3(src: Path, dest: Path) -> None:
    dest.write_bytes(b"MP3 " + src.read_bytes())
