"""Operaciones contra Amazon S3."""
import logging
from typing import Iterable, List

import boto3
from botocore.exceptions import ClientError

from . import config

log = logging.getLogger(__name__)

_s3 = None


def client():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=config.AWS_REGION)
    return _s3


def upload_bytes(key: str, data: bytes, content_type: str) -> str:
    client().put_object(
        Bucket=config.S3_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    log.info("Subido s3://%s/%s (%d bytes)", config.S3_BUCKET, key, len(data))
    return key


def download_bytes(key: str) -> bytes:
    return client().get_object(Bucket=config.S3_BUCKET, Key=key)["Body"].read()


def delete_keys(keys: Iterable[str]) -> List[str]:
    """Borra objetos en lotes de 1000. Devuelve las llaves borradas."""
    keys = [k for k in keys if k]
    deleted: List[str] = []
    for i in range(0, len(keys), 1000):
        chunk = keys[i:i + 1000]
        try:
            client().delete_objects(
                Bucket=config.S3_BUCKET,
                Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": True},
            )
            deleted.extend(chunk)
        except ClientError as exc:
            log.error("No se pudieron borrar objetos de S3: %s", exc)
    return deleted
