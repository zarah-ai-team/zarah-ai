"""
AWS S3 storage client with local-disk fallback.

If AWS credentials / bucket are not configured the client transparently falls
back to storing files under data/uploads/ so development works without AWS.
"""
from __future__ import annotations

import io
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_LOCAL_UPLOAD_DIR = Path(os.getenv("LOCAL_UPLOAD_DIR", "data/uploads"))


class S3StorageClient:
    """
    Unified file storage.  Tries S3 when bucket + credentials are set;
    silently uses local disk otherwise (useful for dev / Docker without IAM).
    """

    def __init__(self):
        self.bucket: Optional[str] = os.getenv("AWS_S3_BUCKET")
        self.region: str = os.getenv("AWS_REGION", "us-east-1")
        self._boto_client = None

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def upload(self, content: bytes, key: str, content_type: str = "application/octet-stream") -> str:
        """Upload bytes and return a URI (s3://… or file://…)."""
        if self._use_s3():
            return self._s3_upload(content, key, content_type)
        return self._local_upload(content, key)

    def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Return a pre-signed URL (S3) or a local path string."""
        if self._use_s3():
            return self._s3_presign(key, expires_in)
        return str(_LOCAL_UPLOAD_DIR / key)

    def delete(self, key: str) -> bool:
        if self._use_s3():
            return self._s3_delete(key)
        return self._local_delete(key)

    def ping(self) -> dict:
        """Return availability status."""
        if not self._use_s3():
            return {"backend": "local", "available": True, "path": str(_LOCAL_UPLOAD_DIR)}
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return {"backend": "s3", "available": True, "bucket": self.bucket, "region": self.region}
        except Exception as e:
            return {"backend": "s3", "available": False, "error": str(e)}

    # ------------------------------------------------------------------ #
    # S3 helpers                                                           #
    # ------------------------------------------------------------------ #

    def _use_s3(self) -> bool:
        return bool(
            self.bucket
            and os.getenv("AWS_ACCESS_KEY_ID")
            and os.getenv("AWS_SECRET_ACCESS_KEY")
        )

    @property
    def _client(self):
        if self._boto_client is None:
            import boto3
            self._boto_client = boto3.client(
                "s3",
                region_name=self.region,
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            )
        return self._boto_client

    def _s3_upload(self, content: bytes, key: str, content_type: str) -> str:
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        logger.info("S3 upload: s3://%s/%s", self.bucket, key)
        return f"s3://{self.bucket}/{key}"

    def _s3_presign(self, key: str, expires_in: int) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def _s3_delete(self, key: str) -> bool:
        self._client.delete_object(Bucket=self.bucket, Key=key)
        return True

    # ------------------------------------------------------------------ #
    # Local fallback helpers                                               #
    # ------------------------------------------------------------------ #

    def _local_upload(self, content: bytes, key: str) -> str:
        dest = _LOCAL_UPLOAD_DIR / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        logger.debug("Local upload: %s", dest)
        return f"file://{dest}"

    def _local_delete(self, key: str) -> bool:
        path = _LOCAL_UPLOAD_DIR / key
        if path.exists():
            path.unlink()
        return True


# Singleton
_storage: Optional[S3StorageClient] = None


def get_storage() -> S3StorageClient:
    global _storage
    if _storage is None:
        _storage = S3StorageClient()
    return _storage
