import subprocess

import pytest

from app.audio import to_mp3
from app.errors import NotAudio


def _probe(path) -> str:
    return subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,codec_type",
            "-of",
            "csv=p=0",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_converts_iphone_m4a_to_mp3(tmp_path):
    src = tmp_path / "tune.m4a"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "aac",
            str(src),
        ],
        check=True,
    )
    dest = tmp_path / "tune.mp3"
    to_mp3(src, dest)
    assert _probe(dest) == "mp3,audio"


def test_drops_video_from_a_phone_video(tmp_path):
    src = tmp_path / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=64x64",
            "-f",
            "lavfi",
            "-i",
            "sine=duration=1",
            "-shortest",
            str(src),
        ],
        check=True,
    )
    dest = tmp_path / "clip.mp3"
    to_mp3(src, dest)
    assert _probe(dest) == "mp3,audio"


def test_rejects_a_file_that_is_not_audio(tmp_path):
    src = tmp_path / "notes.m4a"
    src.write_text("definitely not audio")
    with pytest.raises(NotAudio):
        to_mp3(src, tmp_path / "out.mp3")
