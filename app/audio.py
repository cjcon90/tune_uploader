import subprocess
from pathlib import Path

from app.errors import NotAudio


def to_mp3(src: Path, dest: Path) -> None:
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-i",
                str(src),
                "-vn",
                "-codec:a",
                "libmp3lame",
                "-q:a",
                "2",
                str(dest),
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )
    except subprocess.CalledProcessError as e:
        raise NotAudio(e.stderr.decode(errors="replace")) from e
