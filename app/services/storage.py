import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.models.source import TargetEnum

try:
    import boto3  # type: ignore
except ImportError:  # pragma: no cover
    boto3 = None


class StorageHandler(ABC):
    def __init__(self, source_id: str, run_id: str, target_path: Optional[str]):
        self.source_id = source_id
        self.run_id = run_id
        self.target_path = target_path

    @abstractmethod
    def store_file(self, local_path: str, relative_name: str) -> str: ...


class LocalStorageHandler(StorageHandler):
    def __init__(self, source_id: str, run_id: str, target_path: Optional[str]):
        super().__init__(source_id, run_id, target_path)
        base_path = target_path or f"/app/data/source-{source_id}"
        self.base_path = Path(base_path) / f"run-{run_id}"
        self.base_path.mkdir(parents=True, exist_ok=True)

    def store_file(self, local_path: str, relative_name: str) -> str:
        destination = self.base_path / relative_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, destination)
        return str(destination)


class NASStorageHandler(LocalStorageHandler):
    """Alias of local handler for mounted NAS paths"""


class S3StorageHandler(StorageHandler):
    def __init__(self, source_id: str, run_id: str, target_path: Optional[str]):
        if boto3 is None:
            raise RuntimeError("boto3 is required for S3 storage but is not installed")

        super().__init__(source_id, run_id, target_path)

        bucket = os.getenv("S3_BUCKET")
        prefix = ""

        if target_path:
            parts = target_path.split("/", 1)
            if not bucket:
                bucket = parts[0]
                prefix = parts[1] if len(parts) > 1 else ""
            else:
                prefix = target_path

        if not bucket:
            raise RuntimeError(
                "S3 bucket not configured. Set S3_BUCKET env or include bucket in target_path"
            )

        self.bucket = bucket
        normalized_prefix = prefix.strip("/")
        self.prefix = normalized_prefix
        self.s3 = boto3.client("s3")

    def store_file(self, local_path: str, relative_name: str) -> str:
        key_parts = [
            part
            for part in [
                self.prefix,
                f"source-{self.source_id}",
                f"run-{self.run_id}",
                relative_name,
            ]
            if part
        ]
        key = "/".join(key_parts)
        self.s3.upload_file(local_path, self.bucket, key)
        return f"s3://{self.bucket}/{key}"


def get_storage_handler(
    target: TargetEnum, source_id: str, run_id: str, target_path: Optional[str]
) -> StorageHandler:
    if target == TargetEnum.LOCAL:
        return LocalStorageHandler(source_id, run_id, target_path)
    if target == TargetEnum.NAS:
        return NASStorageHandler(source_id, run_id, target_path)
    if target == TargetEnum.S3:
        return S3StorageHandler(source_id, run_id, target_path)

    raise ValueError(f"Unsupported storage target: {target}")
