import json
from datetime import UTC, datetime

import boto3
from botocore.exceptions import ClientError

TUNES_KEY = "tunes.json"


def make_s3(account_id: str, access_key_id: str, secret_access_key: str):
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
    )


class Store:
    def __init__(self, s3, private_bucket: str, audio_bucket: str) -> None:
        self._s3 = s3
        self._private = private_bucket
        self._audio = audio_bucket

    def load_tunes(self) -> list[dict]:
        try:
            body = self._s3.get_object(Bucket=self._private, Key=TUNES_KEY)["Body"].read()
        except self._s3.exceptions.NoSuchKey:
            return []
        return json.loads(body)["tunes"]

    def save_tunes(self, tunes: list[dict]) -> None:
        if self._exists(self._private, TUNES_KEY):
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            self._s3.copy_object(
                Bucket=self._private,
                Key=f"history/tunes-{stamp}.json",
                CopySource={"Bucket": self._private, "Key": TUNES_KEY},
            )
        self._s3.put_object(
            Bucket=self._private,
            Key=TUNES_KEY,
            Body=json.dumps({"tunes": tunes}, indent=2).encode(),
            ContentType="application/json",
        )

    def put_file(self, tune_id: str, name: str, data: bytes, content_type: str) -> None:
        self._s3.put_object(
            Bucket=self._private, Key=f"{tune_id}/{name}", Body=data, ContentType=content_type
        )

    def get_file(self, tune_id: str, name: str) -> bytes:
        return self._s3.get_object(Bucket=self._private, Key=f"{tune_id}/{name}")["Body"].read()

    def put_audio(self, key: str, data: bytes) -> None:
        self._s3.put_object(
            Bucket=self._audio,
            Key=key,
            Body=data,
            ContentType="audio/mpeg",
            CacheControl="no-cache",
        )

    def copy_audio(self, src_key: str, dest_key: str) -> None:
        self._s3.copy_object(
            Bucket=self._audio, Key=dest_key, CopySource={"Bucket": self._audio, "Key": src_key}
        )

    def audio_exists(self, key: str) -> bool:
        return self._exists(self._audio, key)

    def _exists(self, bucket: str, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=bucket, Key=key)
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise
        return True
