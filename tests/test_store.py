import json

import boto3
import pytest
from moto import mock_aws

from app.store import Store


@pytest.fixture
def s3():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="pm-tunes")
        client.create_bucket(Bucket="pm-audio")
        yield client


@pytest.fixture
def store(s3):
    return Store(s3, "pm-tunes", "pm-audio")


def test_load_tunes_is_empty_before_first_save(store):
    assert store.load_tunes() == []


def test_save_then_load_round_trips(store):
    store.save_tunes([{"id": "k7mq3xpw", "title": "The Kesh"}])
    assert store.load_tunes() == [{"id": "k7mq3xpw", "title": "The Kesh"}]


def test_save_keeps_the_previous_list_in_history(store, s3):
    store.save_tunes([{"id": "a"}])
    store.save_tunes([{"id": "a"}, {"id": "b"}])
    keys = [o["Key"] for o in s3.list_objects_v2(Bucket="pm-tunes", Prefix="history/")["Contents"]]
    assert len(keys) == 1
    old = json.loads(s3.get_object(Bucket="pm-tunes", Key=keys[0])["Body"].read())
    assert old == {"tunes": [{"id": "a"}]}


def test_audio_is_public_mp3_never_cached(store, s3):
    store.put_audio("k7mq3xpw", b"ID3fake")
    head = s3.head_object(Bucket="pm-audio", Key="k7mq3xpw")
    assert head["ContentType"] == "audio/mpeg"
    assert head["CacheControl"] == "no-cache"


def test_copy_audio_keeps_headers(store, s3):
    store.put_audio("k7mq3xpw", b"ID3fake")
    store.copy_audio("k7mq3xpw", "the-kesh")
    head = s3.head_object(Bucket="pm-audio", Key="the-kesh")
    assert head["ContentType"] == "audio/mpeg"
    assert head["CacheControl"] == "no-cache"


def test_audio_exists(store):
    assert not store.audio_exists("the-kesh")
    store.put_audio("the-kesh", b"ID3fake")
    assert store.audio_exists("the-kesh")


def test_private_files_live_under_the_tune_id(store, s3):
    store.put_file("k7mq3xpw", "sheet.pdf", b"%PDF", "application/pdf")
    assert store.get_file("k7mq3xpw", "sheet.pdf") == b"%PDF"
    assert s3.list_objects_v2(Bucket="pm-audio").get("KeyCount") == 0
