import shutil
from pathlib import Path

import boto3
import pytest
from moto import mock_aws
from werkzeug.security import generate_password_hash

from app import config, create_app
from app.library import Library
from app.store import Store
from tests.fakes import FakeRedirects, fake_render, fake_to_mp3

FIXTURE = Path(__file__).parent / "fixtures" / "original.xml"

needs_render = pytest.mark.skipif(
    shutil.which("mscore") is None or shutil.which("pdftoppm") is None,
    reason="MuseScore/poppler only in the container",
)


@pytest.fixture
def fixture_xml() -> bytes:
    return FIXTURE.read_bytes()


XML = b"<score-partwise/>"


@pytest.fixture
def library():
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="pm-tunes")
        s3.create_bucket(Bucket="pm-audio")
        yield Library(
            Store(s3, "pm-tunes", "pm-audio"),
            FakeRedirects(),
            "audio.paulinemahon.com",
            render=fake_render,
            to_mp3=fake_to_mp3,
        )


@pytest.fixture
def app(library, monkeypatch):
    monkeypatch.setattr(config, "PASSWORD_HASH", generate_password_hash("fiddle"))
    monkeypatch.setattr(config, "SECRET_KEY", "test")
    sent = []
    monkeypatch.setattr("app.notify.send", lambda title, message: sent.append(message))
    flask_app = create_app(library)
    flask_app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    flask_app.sent = sent
    return flask_app


@pytest.fixture
def client(app):
    c = app.test_client()
    c.post("/login", data={"password": "fiddle"})
    return c
