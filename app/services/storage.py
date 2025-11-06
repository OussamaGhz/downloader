import os
import shutil
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.models.source import TargetEnum

try:
    import boto3  # type: ignore
except ImportError:  # pragma: no cover
    boto3 = None

try:
    from smbprotocol.connection import Connection  # type: ignore
    from smbprotocol.session import Session  # type: ignore
    from smbprotocol.tree import TreeConnect  # type: ignore
    from smbprotocol.open import Open, CreateDisposition, FileAttributes, ImpersonationLevel, CreateOptions, ShareAccess, FilePipePrinterAccessMask  # type: ignore
    from smbprotocol.file_info import FileStandardInformation  # type: ignore
except ImportError:  # pragma: no cover
    Connection = Session = TreeConnect = Open = None

# NAS/SMB Configuration Constants
NAS_SERVER = os.getenv("NAS_SERVER", "172.16.11.226")
NAS_SHARE = os.getenv("NAS_SHARE", "downloader")
NAS_USERNAME = os.getenv("NAS_USERNAME", "keystone")
NAS_PASSWORD = os.getenv("NAS_PASSWORD", "Pass1234")
NAS_PORT = int(os.getenv("NAS_PORT", "445"))


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


class NASStorageHandler(StorageHandler):
    """Storage handler that uploads files to a NAS share via SMB protocol."""

    def __init__(self, source_id: str, run_id: str, target_path: Optional[str]):
        if Connection is None:
            raise RuntimeError(
                "smbprotocol is required for NAS storage but is not installed"
            )

        super().__init__(source_id, run_id, target_path)

        self.server = NAS_SERVER
        self.share = NAS_SHARE
        self.username = NAS_USERNAME
        self.password = NAS_PASSWORD
        self.port = NAS_PORT

        # Construct remote base path - all files for a source go in one directory
        if target_path:
            self.remote_base = f"{target_path}/source-{source_id}"
        else:
            self.remote_base = f"source-{source_id}"

    def store_file(self, local_path: str, relative_name: str) -> str:
        """Upload a file to the NAS share via SMB."""
        connection = Connection(uuid.uuid4(), self.server, self.port)

        try:
            connection.connect()
            
            # Create and register session properly
            session = Session(connection, self.username, self.password)
            session.connect()
            
            # Connect to the share
            tree = TreeConnect(session, f"\\\\{self.server}\\{self.share}")
            tree.connect()

            # Build remote path
            remote_path = f"{self.remote_base}/{relative_name}".replace("\\", "/")
            remote_parts = remote_path.split("/")

            # Create directories if needed
            current_dir = ""
            for part in remote_parts[:-1]:
                if not part:
                    continue
                current_dir = f"{current_dir}/{part}" if current_dir else part

                try:
                    dir_open = Open(tree, current_dir)
                    dir_open.create(
                        desired_access=FilePipePrinterAccessMask.GENERIC_READ,
                        file_attributes=FileAttributes.FILE_ATTRIBUTE_DIRECTORY,
                        share_access=ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE,
                        create_disposition=CreateDisposition.FILE_OPEN_IF,
                        create_options=CreateOptions.FILE_DIRECTORY_FILE,
                        impersonation_level=ImpersonationLevel.Impersonation,
                    )

                    dir_open.close()
                except Exception:
                    pass  # Directory might already exist

            # Upload the file
            file_open = Open(tree, remote_path)
            file_open.create(
                desired_access=FilePipePrinterAccessMask.GENERIC_WRITE,
                file_attributes=FileAttributes.FILE_ATTRIBUTE_NORMAL,
                share_access=ShareAccess.FILE_SHARE_READ | ShareAccess.FILE_SHARE_WRITE,
                create_disposition=CreateDisposition.FILE_OVERWRITE_IF,
                create_options=0,
                impersonation_level=ImpersonationLevel.Impersonation,
            )


            with open(local_path, "rb") as local_file:
                offset = 0
                while True:
                    chunk = local_file.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    file_open.write(chunk, offset)
                    offset += len(chunk)

            file_open.close()
            tree.disconnect()
            session.disconnect()

            return f"smb://{self.server}/{self.share}/{remote_path}"

        finally:
            try:
                connection.disconnect()
            except Exception:
                pass  # Connection might already be closed


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
