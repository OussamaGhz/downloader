import os
import shutil
import uuid
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.models.source import TargetEnum


def sanitize_name(name: str) -> str:
    """Sanitize source/file names for filesystem compatibility.

    Removes or replaces characters that are invalid in Windows/SMB paths:
    - Replaces spaces with underscores
    - Removes: < > : " / \\ | ? * & # % @ ! $ ^ ( ) [ ] { } ; ' ` ~
    - Removes control characters
    - Ensures only alphanumeric, underscore, hyphen, and dot remain
    """
    # Replace spaces with underscores
    name = name.replace(" ", "_")
    # Remove invalid Windows/SMB filename characters and common problematic chars
    name = re.sub(r'[<>:"/\\|?*&#%@!$^()\[\]{};\'`~]', "", name)
    # Only allow alphanumeric, underscore, hyphen, dot, and common safe chars
    name = re.sub(r"[^\w\-.]", "", name)
    # Collapse multiple underscores
    name = re.sub(r"_+", "_", name)
    # Strip leading/trailing underscores and dots
    name = name.strip("_.")
    # Ensure name is not empty
    return name or "unnamed"


def sanitize_path(path: str) -> str:
    """Sanitize a full path while preserving directory structure.

    Splits the path into components, sanitizes each separately,
    and rebuilds the path with forward slashes.

    Args:
        path: Path string (e.g., "folder/subfolder/file.txt")

    Returns:
        Sanitized path with directory structure preserved
        (e.g., "folder/subfolder/file.txt")
    """
    # Handle both forward and backslash separators
    # Normalize to forward slashes first
    normalized = path.replace("\\", "/")

    # Split into components
    parts = normalized.split("/")

    # Sanitize each component individually
    sanitized_parts = [sanitize_name(part) for part in parts if part]

    # Rebuild path with forward slashes
    return "/".join(sanitized_parts)


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

# Import NAS configuration from centralized config
from app.core.config import (
    NAS_SERVER,
    NAS_SHARE,
    NAS_USERNAME,
    NAS_PASSWORD,
    NAS_PORT,
)


class StorageHandler(ABC):
    def __init__(
        self,
        source_id: str,
        source_name: str,
        run_id: str,
        target_path: Optional[str],
    ):
        self.source_id = source_id
        self.source_name = sanitize_name(source_name)
        self.run_id = run_id
        self.target_path = target_path

    @abstractmethod
    def store_file(self, local_path: str, relative_name: str) -> str: ...


class LocalStorageHandler(StorageHandler):
    def __init__(
        self,
        source_id: str,
        source_name: str,
        run_id: str,
        target_path: Optional[str],
    ):
        super().__init__(source_id, source_name, run_id, target_path)
        # Use the sanitized name from parent class
        base_path = target_path or f"/app/data/source_{self.source_name}"
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def store_file(self, local_path: str, relative_name: str) -> str:
        # Sanitize the path while preserving directory structure
        safe_name = sanitize_path(relative_name)
        destination = self.base_path / safe_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, destination)
        return str(destination)


class NASStorageHandler(StorageHandler):
    """Storage handler that uploads files to a NAS share via SMB protocol."""

    def __init__(
        self,
        source_id: str,
        source_name: str,
        run_id: str,
        target_path: Optional[str],
    ):
        if Connection is None:
            raise RuntimeError(
                "smbprotocol is required for NAS storage but is not installed"
            )

        super().__init__(source_id, source_name, run_id, target_path)

        self.server = NAS_SERVER
        self.share = NAS_SHARE
        self.username = NAS_USERNAME
        self.password = NAS_PASSWORD
        self.port = NAS_PORT

        # Construct remote base path - all files for a source go in one directory
        # Use the sanitized name from parent class
        # Add "Downloader" as base directory for organization
        if target_path:
            self.remote_base = f"Downloader/{target_path}/source_{self.source_name}"
        else:
            self.remote_base = f"Downloader/source_{self.source_name}"

    def store_file(self, local_path: str, relative_name: str) -> str:
        """Upload a file to the NAS share via SMB."""
        # Sanitize the path while preserving directory structure
        safe_name = sanitize_path(relative_name)

        # Debug logging
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"NAS upload - Original name: {relative_name}")
        logger.info(f"NAS upload - Sanitized name: {safe_name}")
        logger.info(f"NAS upload - Remote base: {self.remote_base}")

        connection = Connection(uuid.uuid4(), self.server, self.port)

        try:
            connection.connect()

            # Create and register session properly
            session = Session(connection, self.username, self.password)
            session.connect()

            # Connect to the share
            tree = TreeConnect(session, f"\\\\{self.server}\\{self.share}")
            tree.connect()

            # Build remote path with sanitized name
            remote_path = f"{self.remote_base}/{safe_name}".replace("\\", "/")
            logger.info(f"NAS upload - Full remote path: {remote_path}")
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
                        share_access=ShareAccess.FILE_SHARE_READ
                        | ShareAccess.FILE_SHARE_WRITE,
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
    def __init__(
        self,
        source_id: str,
        source_name: str,
        run_id: str,
        target_path: Optional[str],
    ):
        if boto3 is None:
            raise RuntimeError("boto3 is required for S3 storage but is not installed")

        super().__init__(source_id, source_name, run_id, target_path)

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
        # Sanitize the path while preserving directory structure
        safe_name = sanitize_path(relative_name)
        key_parts = [
            part
            for part in [
                self.prefix,
                f"source_{self.source_name}",
                safe_name,
            ]
            if part
        ]
        key = "/".join(key_parts)
        self.s3.upload_file(local_path, self.bucket, key)
        return f"s3://{self.bucket}/{key}"


def get_storage_handler(
    target: TargetEnum,
    source_id: str,
    source_name: str,
    run_id: str,
    target_path: Optional[str],
) -> StorageHandler:
    if target == TargetEnum.LOCAL:
        return LocalStorageHandler(source_id, source_name, run_id, target_path)
    if target == TargetEnum.NAS:
        return NASStorageHandler(source_id, source_name, run_id, target_path)
    if target == TargetEnum.S3:
        return S3StorageHandler(source_id, source_name, run_id, target_path)

    raise ValueError(f"Unsupported storage target: {target}")
