import asyncio
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from prefect import flow, task, get_run_logger
from prefect.concurrency.sync import concurrency
from prefect.context import get_run_context
from prefect.exceptions import CancelledRun
from telethon import TelegramClient  # type: ignore[import]
from telethon.sessions import StringSession  # type: ignore[import]
from telethon.tl.types import PeerChannel  # type: ignore[import]

try:  # pragma: no cover - fallback for typing environments without rpcerrorlist stubs
    from telethon.errors.rpcerrorlist import TimeoutError as TelethonTimeoutError  # type: ignore[import]
except ImportError:  # pragma: no cover
    from telethon.errors import RPCError  # type: ignore[import]

    class TelethonTimeoutError(RPCError):
        """Fallback TimeoutError shim when rpcerrorlist is unavailable."""

        pass


from app.core.database import SessionLocal
from app.models.source import AccessLevelEnum, Source, TargetEnum
from app.models.session import TelegramSession
from app.services.encryption import decrypt_data
from app.services.file_utils import (
    ARCHIVE_MULTI_SUFFIXES,
    filter_allowed_files,
    is_archive,
    sha256_checksum,
    extract_archive,
    extract_archive_recursive,
    extract_password_from_message,
)
from app.services.scrape_progress import (
    LogLevel,
    ScrapeStatus,
    create_scrape_run,
    get_processed_file_keys,
    get_processed_archive_checksums,
    log_event,
    mark_run_complete,
    record_scraped_file,
    update_run_counts,
)
from app.services.storage import get_storage_handler


# Batch and concurrency settings
MAX_FILES_PER_RUN = 10  # Reduced for large files (500MB-2GB each)
DOWNLOAD_CONCURRENCY = 3

# Retry settings
DOWNLOAD_RETRY_ATTEMPTS = 3
DOWNLOAD_RETRY_BASE_DELAY = 2

# Timeout configurations (adjusted for large files)
DOWNLOAD_TIMEOUT_PER_FILE = 1800  # 30 min per file (for 2GB files)
DOWNLOAD_TASK_BASE_TIMEOUT = 14400  # 4 hours for entire download phase
PROCESS_FILE_TIMEOUT = 3600  # 1 hour per file processing (extract + upload)


def _chunked(sequence: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(sequence), size):
        yield sequence[index : index + size]


@dataclass
class SourceConfig:
    id: str
    name: str
    access_level: str
    identifier: str
    api_id: int
    api_hash: str
    session_string: Optional[str]
    bot_token: Optional[str]
    target: str
    target_path: Optional[str]
    file_types: List[str]

    @property
    def allowed_extensions(self) -> List[str]:
        return [ext.lower().lstrip(".") for ext in self.file_types if ext]


@dataclass
class PendingFile:
    message_id: int
    file_id: str
    file_name: str
    file_extension: str
    size: Optional[int]
    date: Optional[datetime]
    message_text: Optional[str] = None  # For password extraction


def _build_client(config: SourceConfig) -> TelegramClient:
    session = (
        StringSession(config.session_string)
        if config.session_string
        else StringSession()
    )
    return TelegramClient(session, config.api_id, config.api_hash)


async def _ensure_client_ready(client: TelegramClient, config: SourceConfig):
    if config.session_string:
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError(
                "Stored session is not authorized. Re-authenticate the private session."
            )
    elif config.bot_token:
        await client.start(bot_token=config.bot_token)
    else:
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError(
                "Public source requires a bot token or shared session for access."
            )


async def _resolve_entity(client: TelegramClient, identifier: str):
    try:
        if identifier.startswith("@"):
            return await client.get_entity(identifier)
        if identifier.isdigit():
            return await client.get_entity(PeerChannel(int(identifier)))
        return await client.get_entity(identifier)
    except ValueError:
        return await client.get_entity(identifier)


def _normalized_processed_keys(keys: Sequence[Sequence[Any]]) -> Set[Tuple[int, str]]:
    normalized: Set[Tuple[int, str]] = set()
    for item in keys:
        if len(item) != 2:
            continue
        message_id, file_id = item
        try:
            normalized.add((int(message_id), str(file_id)))
        except (TypeError, ValueError):  # pragma: no cover - defensive
            continue
    return normalized


def _safe_file_identifier(message: Any) -> Tuple[str, Optional[str]]:

    try:
        identifier = getattr(message.file, "id", None)
        if identifier:
            return str(identifier), None
    except Exception as exc:  # pragma: no cover - defensive
        fallback_reason = f"file.id failure: {exc.__class__.__name__}"
    else:
        fallback_reason = None

    for candidate in (
        getattr(getattr(message, "file", None), "unique_id", None),
        getattr(getattr(message, "document", None), "id", None),
        getattr(getattr(getattr(message, "media", None), "document", None), "id", None),
        getattr(getattr(message, "photo", None), "id", None),
        getattr(getattr(getattr(message, "media", None), "photo", None), "id", None),
    ):
        if candidate:
            return str(candidate), fallback_reason

    dc_component = getattr(getattr(message, "file", None), "dc_id", None)
    return f"msg-{message.id}-{dc_component or 'unknown'}", fallback_reason


def _log_and_record(
    run_id: str,
    message: str,
    level: LogLevel = LogLevel.INFO,
    details: Optional[Dict[str, Any]] = None,
):
    logger = get_run_logger()
    if level == LogLevel.ERROR:
        logger.error(message)
    elif level == LogLevel.WARNING:
        logger.warning(message)
    else:
        logger.info(message)
    log_event(run_id=run_id, message=message, level=level, details=details)


@task
def initialize_run(source_id: str) -> Dict[str, Any]:
    run_context = get_run_context()
    flow_run_id = None
    if run_context:
        if hasattr(run_context, "flow_run_id"):
            flow_run_id = run_context.flow_run_id
        elif hasattr(run_context, "flow_run"):
            flow_run = getattr(run_context, "flow_run")
            flow_run_id = getattr(flow_run, "id", None)
        elif hasattr(run_context, "task_run"):
            task_run = getattr(run_context, "task_run")
            flow_run_id = getattr(task_run, "flow_run_id", None)

    with SessionLocal() as db:
        source = db.query(Source).filter(Source.id == source_id).first()
        if not source:
            raise RuntimeError(f"Source {source_id} not found")

        api_id = int(decrypt_data(source.api_id)) if source.api_id else None
        api_hash = decrypt_data(source.api_hash) if source.api_hash else None
        bot_token = decrypt_data(source.bot_token) if source.bot_token else None

        session_string = None
        if source.access_level == AccessLevelEnum.PRIVATE:
            if not source.session_ref:
                raise RuntimeError("Private source requires a linked Telegram session")
            session = (
                db.query(TelegramSession)
                .filter(TelegramSession.id == source.session_ref)
                .first()
            )
            if not session:
                raise RuntimeError("Linked Telegram session not found")
            session_string = decrypt_data(session.session_string)
            # Prefer session API credentials when available
            api_id = session.api_id
            api_hash = decrypt_data(session.api_hash)

        if api_id is None or api_hash is None:
            raise RuntimeError("Source is missing Telegram API credentials")

        file_types = source.file_types or []

        logger = get_run_logger()
        logger.debug(f"Source file types: {file_types}")

        config = SourceConfig(
            id=str(source.id),
            name=source.name,
            access_level=source.access_level.value,
            identifier=source.identifier,
            api_id=int(api_id),
            api_hash=api_hash,
            session_string=session_string,
            bot_token=bot_token,
            target=source.target.value,
            target_path=source.target_path,
            file_types=file_types,
        )

    source_uuid = str(source.id)
    run = create_scrape_run(source_id=source_uuid, flow_run_id=flow_run_id)
    processed = get_processed_file_keys(source_uuid)
    processed_archives = get_processed_archive_checksums(source_uuid)

    _log_and_record(
        run_id=str(run.id),
        message=f"Scrape run initialized. Found {len(processed)} processed files, {len(processed_archives)} processed archives",
    )

    return {
        "run_id": str(run.id),
        "config": asdict(config),
        "processed_keys": [(msg_id, file_id) for msg_id, file_id in processed],
        "processed_archives": list(processed_archives),
    }


@task
def collect_new_files(initial_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    config = SourceConfig(**initial_data["config"])
    processed_keys = _normalized_processed_keys(initial_data["processed_keys"])
    run_id = initial_data["run_id"]

    _log_and_record(run_id, "Scan started")

    async def _collect() -> List[PendingFile]:
        client = _build_client(config)
        await _ensure_client_ready(client, config)
        entity = await _resolve_entity(client, config.identifier)

        new_files: List[PendingFile] = []
        async for message in client.iter_messages(entity, limit=500):
            if not message.file:
                continue
            file_id, fallback_reason = _safe_file_identifier(message)
            if fallback_reason:
                _log_and_record(
                    run_id,
                    (f"Using fallback identifier for message {message.id}: {file_id}"),
                    LogLevel.DEBUG,
                    details={"reason": fallback_reason},
                )
            key = (message.id, file_id)
            if key in processed_keys:
                _log_and_record(
                    run_id,
                    f"Skipping previously processed file from message {message.id}",
                    LogLevel.DEBUG,
                    details={"file_id": file_id},
                )
                continue

            file_name = message.file.name or f"message_{message.id}"
            lower_name = file_name.lower()
            extension = next(
                (
                    suffix
                    for suffix in ARCHIVE_MULTI_SUFFIXES
                    if lower_name.endswith(suffix)
                ),
                None,
            )
            if not extension:
                extension = (Path(file_name).suffix or message.file.ext or "").lower()
            normalized_ext = extension.lstrip(".")

            if (
                config.allowed_extensions
                and normalized_ext not in config.allowed_extensions
                and not is_archive(file_name)
            ):
                continue

            # Capture message text for potential password extraction
            message_text = message.message if hasattr(message, "message") else None

            new_files.append(
                PendingFile(
                    message_id=message.id,
                    file_id=file_id,
                    file_name=file_name,
                    file_extension=extension,
                    size=message.file.size,
                    date=message.date,
                    message_text=message_text,
                )
            )

        await client.disconnect()
        return new_files

    pending_files: List[PendingFile] = asyncio.run(_collect())

    update_run_counts(run_id, files_found=len(pending_files))
    if pending_files:
        _log_and_record(run_id, f"Found {len(pending_files)} new file(s) to process")
    else:
        _log_and_record(run_id, "No new files found")

    return [asdict(file) for file in pending_files]


@task(
    name="download_files_sequential",
    timeout_seconds=DOWNLOAD_TASK_BASE_TIMEOUT,
    retries=2,
    retry_delay_seconds=60,
)
async def download_files_sequential(
    config_dict: Dict[str, Any],
    run_id: str,
    selected_files: List[Dict[str, Any]],
    temp_dir_path: str,
    processed_archives: Set[str],
) -> List[Tuple[Dict[str, Any], Path]]:
    """
    Download all files SEQUENTIALLY using ONE Telethon client.
    This avoids DC migration conflicts and AuthBytesInvalidError.
    Returns list of (file_item, local_path) tuples for successful downloads.
    """
    config = SourceConfig(**config_dict)
    client = _build_client(config)

    try:
        await _ensure_client_ready(client, config)
        entity = await _resolve_entity(client, config.identifier)

        results = []
        total = len(selected_files)

        _log_and_record(
            run_id,
            f"Starting sequential download of {total} files with ONE Telethon client...",
        )

        for idx, file_item in enumerate(selected_files, 1):
            message_id = file_item["message_id"]
            file_id = file_item["file_id"]
            file_name = file_item["file_name"]

            _log_and_record(
                run_id,
                f"[Download {idx}/{total}] Starting message {message_id}: {file_name}",
            )

            # Download with retry logic
            attempt = 0
            delay = DOWNLOAD_RETRY_BASE_DELAY
            local_path = None

            while attempt < DOWNLOAD_RETRY_ATTEMPTS:
                try:
                    message = await client.get_messages(entity, ids=message_id)
                    if not message or not message.file:
                        _log_and_record(
                            run_id,
                            f"[Download {idx}/{total}] Skipping: no file attachment",
                            LogLevel.WARNING,
                        )
                        break

                    # Extract metadata from message for later use
                    file_item["timestamp"] = (
                        message.date.isoformat() if message.date else None
                    )
                    file_item["message_text"] = (
                        message.message if hasattr(message, "message") else None
                    )
                    file_item["channel_name"] = config.name

                    destination = Path(temp_dir_path) / f"{message_id}_{file_id}"

                    # Add per-file timeout to prevent hanging on large files
                    download_path = await asyncio.wait_for(
                        client.download_media(message, file=str(destination)),
                        timeout=DOWNLOAD_TIMEOUT_PER_FILE,  # 30 min per file
                    )
                    local_path = Path(download_path)

                    size_mb = local_path.stat().st_size / 1024 / 1024

                    # Calculate archive checksum if it's an archive file
                    archive_checksum = None
                    if is_archive(file_name):
                        _log_and_record(
                            run_id,
                            f"[Download {idx}/{total}] Calculating archive checksum...",
                            LogLevel.DEBUG,
                        )
                        archive_checksum = await asyncio.to_thread(
                            sha256_checksum, local_path
                        )

                        # Check if this archive was already processed
                        if archive_checksum in processed_archives:
                            _log_and_record(
                                run_id,
                                f"[Download {idx}/{total}] ⚠️ Archive already processed (checksum: {archive_checksum[:16]}...)",
                                LogLevel.WARNING,
                                details={
                                    "file_name": file_name,
                                    "checksum": archive_checksum,
                                    "action": "skipped_duplicate",
                                },
                            )
                            break  # Skip this archive

                    _log_and_record(
                        run_id,
                        f"[Download {idx}/{total}] ✓ Downloaded: {local_path.name} ({size_mb:.1f} MB)",
                    )

                    # Store checksum in file_item for later use
                    file_item["archive_checksum"] = archive_checksum

                    results.append((file_item, local_path))
                    break

                except (TelethonTimeoutError, asyncio.TimeoutError) as exc:
                    attempt += 1
                    _log_and_record(
                        run_id,
                        f"[Download {idx}/{total}] Timeout (attempt {attempt}/{DOWNLOAD_RETRY_ATTEMPTS}): {exc}",
                        LogLevel.WARNING,
                    )
                    if attempt < DOWNLOAD_RETRY_ATTEMPTS:
                        await asyncio.sleep(delay)
                        delay *= 2
                    else:
                        _log_and_record(
                            run_id,
                            f"[Download {idx}/{total}] ✗ Failed after {DOWNLOAD_RETRY_ATTEMPTS} attempts",
                            LogLevel.ERROR,
                        )
                        break

                except Exception as exc:
                    _log_and_record(
                        run_id,
                        f"[Download {idx}/{total}] ✗ Error: {exc}",
                        LogLevel.ERROR,
                    )
                    break

        _log_and_record(
            run_id,
            f"Download phase complete: {len(results)}/{total} files downloaded successfully",
        )

        return results

    finally:
        await client.disconnect()


@task(
    retries=2,
    retry_delay_seconds=60,
    timeout_seconds=PROCESS_FILE_TIMEOUT,
    name="process_downloaded_file",
)
async def process_downloaded_file(
    config_dict: Dict[str, Any],
    run_id: str,
    file_item: Dict[str, Any],
    local_path: Path,
    temp_dir_path: str,
    file_index: int,
    total_files: int,
) -> Dict[str, Any]:
    """
    Process an already-downloaded file: extract, store, checksum, and record.
    No Telethon client needed - can run in parallel safely.
    This task provides granular visibility and automatic retries per file.
    """
    config = SourceConfig(**config_dict)
    message_id = file_item["message_id"]
    file_id = file_item["file_id"]
    file_name = file_item["file_name"]

    _log_and_record(
        run_id,
        f"[Process {file_index}/{total_files}] Starting: {file_name}",
        LogLevel.INFO,
    )

    try:
        # Get storage handler
        storage = get_storage_handler(
            target=TargetEnum(config.target),
            source_id=config.id,
            source_name=config.name,
            run_id=run_id,
            target_path=config.target_path,
        )

        stored_count = 0
        extension = local_path.suffix.lower()

        # Process based on file type
        if is_archive(local_path.name):
            _log_and_record(
                run_id,
                f"[Process {file_index}/{total_files}] Extracting archive: {local_path.name}",
            )

            # Use original file name (without extension) for extraction directory
            archive_name_without_ext = local_path.stem
            # Handle multi-part extensions like .tar.gz
            for multi_suffix in ARCHIVE_MULTI_SUFFIXES:
                if local_path.name.lower().endswith(multi_suffix):
                    archive_name_without_ext = local_path.name[: -len(multi_suffix)]
                    break

            # Extract potential passwords from message text
            passwords = []
            message_text = file_item.get("message_text")
            if message_text:
                passwords = extract_password_from_message(message_text)
                if passwords:
                    _log_and_record(
                        run_id,
                        f"[Process {file_index}/{total_files}] Found {len(passwords)} potential password(s) in message",
                        LogLevel.INFO,
                    )

            # Calculate archive size for metadata
            archive_size_mb = local_path.stat().st_size / 1024 / 1024
            password_protected = False

            try:
                # Use recursive extraction - it will create the extraction directory
                extracted_paths = await asyncio.to_thread(
                    extract_archive_recursive,
                    local_path,
                    Path(temp_dir_path),
                    passwords,
                )
                _log_and_record(
                    run_id,
                    f"[Process {file_index}/{total_files}] Extracted {len(extracted_paths)} file(s) (including nested archives)",
                )
            except RuntimeError as exc:
                # Handle password-protected archives specifically
                error_msg = str(exc)
                if "password" in error_msg.lower():
                    password_protected = True

                    # Enhanced error logging with suggestions
                    suggestion = ""
                    if len(passwords) == 0:
                        suggestion = " | Suggestion: Add password to Telegram message using format 'password: yourpass'"
                    else:
                        suggestion = f" | Tried passwords: {', '.join(passwords)}"

                    _log_and_record(
                        run_id,
                        f"[Process {file_index}/{total_files}] {error_msg}{suggestion}",
                        LogLevel.ERROR,
                        details={
                            "archive": local_path.name,
                            "passwords_tried": len(passwords),
                            "password_candidates": passwords if passwords else None,
                            "message_text": (
                                message_text[:200] if message_text else None
                            ),
                            "suggestion": "Add password to message or contact source admin",
                        },
                    )
                else:
                    _log_and_record(
                        run_id,
                        f"[Process {file_index}/{total_files}] Extraction failed: {exc}",
                        LogLevel.ERROR,
                    )
                return {
                    "success": False,
                    "reason": "extraction_failed",
                    "message_id": message_id,
                    "error": error_msg,
                    "password_protected": password_protected,
                }
            except Exception as exc:
                _log_and_record(
                    run_id,
                    f"[Process {file_index}/{total_files}] Extraction failed: {exc}",
                    LogLevel.ERROR,
                )
                return {
                    "success": False,
                    "reason": "extraction_failed",
                    "message_id": message_id,
                }

            allowed = filter_allowed_files(
                extracted_paths, config.file_types or ["txt"]
            )

            if not allowed:
                _log_and_record(
                    run_id,
                    f"[Process {file_index}/{total_files}] No allowed files in archive",
                    LogLevel.INFO,
                )
                return {
                    "success": True,
                    "stored": 0,
                    "message_id": message_id,
                    "reason": "no_allowed_files",
                }

            _log_and_record(
                run_id,
                f"[Process {file_index}/{total_files}] Storing {len(allowed)} extracted file(s)...",
            )

            # The extraction directory is: temp_dir_path/archive_name_extracted/
            extraction_base_dir = (
                Path(temp_dir_path) / f"{archive_name_without_ext}_extracted"
            )

            for extracted_file in allowed:
                # Preserve folder structure from archive (including nested archives)
                try:
                    # Get path relative to temp directory to preserve full structure
                    relative_path = extracted_file.relative_to(Path(temp_dir_path))
                    # Use the relative path directly (it already includes archive_name_extracted/)
                    structured_name = str(relative_path)
                except ValueError:
                    # Fallback if relative_to fails
                    structured_name = (
                        f"{archive_name_without_ext}_extracted/{extracted_file.name}"
                    )

                storage_path = await asyncio.to_thread(
                    storage.store_file, str(extracted_file), structured_name
                )
                checksum = await asyncio.to_thread(sha256_checksum, extracted_file)

                # Get archive checksum from file_item
                archive_checksum = file_item.get("archive_checksum")

                # Determine relative path within extraction directory
                try:
                    rel_path_str = str(extracted_file.relative_to(extraction_base_dir))
                except ValueError:
                    rel_path_str = extracted_file.name

                # Build comprehensive archive metadata
                archive_metadata = {
                    "archived": True,
                    "archive_name": local_path.name,
                    "archive_size_mb": round(archive_size_mb, 2),
                    "archive_checksum": archive_checksum,
                    "password_protected": password_protected,
                    "relative_path": rel_path_str,
                    "extraction_dir": f"{archive_name_without_ext}_extracted",
                    # Enhanced metadata
                    "channel_name": file_item.get("channel_name", config.name),
                    "message_id": message_id,
                    "file_id": file_id,
                    "timestamp": file_item.get("timestamp"),
                    "message_text": file_item.get("message_text"),
                    "download_date": datetime.now(timezone.utc).isoformat(),
                }

                # Add password info if applicable
                if passwords:
                    archive_metadata["passwords_found"] = len(passwords)

                file_record = await asyncio.to_thread(
                    record_scraped_file,
                    run_id=run_id,
                    source_id=config.id,
                    message_id=message_id,
                    file_id=file_id,
                    file_name=extracted_file.name,
                    storage_path=storage_path,
                    file_extension=extracted_file.suffix.lower(),
                    size_bytes=extracted_file.stat().st_size,
                    checksum=checksum,
                    extracted_from=local_path.name,
                    extra_metadata=archive_metadata,
                    archive_checksum=archive_checksum,
                )

                if file_record:
                    stored_count += 1
                    _log_and_record(
                        run_id,
                        f"[Process {file_index}/{total_files}] Stored: {structured_name}",
                        LogLevel.DEBUG,
                    )

        else:
            # Regular file processing
            normalized_ext = extension.lstrip(".")
            if (
                config.allowed_extensions
                and normalized_ext not in config.allowed_extensions
            ):
                _log_and_record(
                    run_id,
                    f"[Process {file_index}/{total_files}] Skipping: extension {extension} not allowed",
                    LogLevel.INFO,
                )
                return {
                    "success": True,
                    "stored": 0,
                    "message_id": message_id,
                    "reason": "extension_not_allowed",
                }

            _log_and_record(
                run_id,
                f"[Process {file_index}/{total_files}] Storing file: {local_path.name}",
            )

            # Calculate checksum
            checksum = await asyncio.to_thread(sha256_checksum, local_path)

            # Get metadata from file_item
            channel_name = file_item.get("channel_name", config.name)
            timestamp = file_item.get("timestamp")

            # Sanitize channel name for filename (remove special chars)
            safe_channel = (
                channel_name.replace(" ", "_").replace("/", "_").replace("\\", "_")
            )
            safe_channel = "".join(
                c for c in safe_channel if c.isalnum() or c in ("_", "-")
            )

            # Format timestamp for filename (YYYYMMDDTHHmmss)
            if timestamp:
                # Parse ISO timestamp and format it
                from datetime import datetime

                try:
                    dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    timestamp_str = dt.strftime("%Y%m%dT%H%M%S")
                except:
                    timestamp_str = "unknown"
            else:
                timestamp_str = "unknown"

            # Get file extension
            file_ext = local_path.suffix  # .txt, .pdf, etc.

            # Create filename: {channel}_{msgid}_{timestamp}.ext
            structured_filename = (
                f"{safe_channel}_{message_id}_{timestamp_str}{file_ext}"
            )

            storage_path = await asyncio.to_thread(
                storage.store_file, str(local_path), structured_filename
            )

            # Build metadata
            extra_metadata = {
                "channel_name": channel_name,
                "message_id": message_id,
                "file_id": file_id,
                "timestamp": timestamp,
                "message_text": file_item.get("message_text"),
                "download_date": datetime.now(timezone.utc).isoformat(),
                "original_filename": file_name,
            }

            file_record = await asyncio.to_thread(
                record_scraped_file,
                run_id=run_id,
                source_id=config.id,
                message_id=message_id,
                file_id=file_id,
                file_name=local_path.name,
                storage_path=storage_path,
                file_extension=extension,
                size_bytes=local_path.stat().st_size,
                checksum=checksum,
                extra_metadata=extra_metadata,
            )

            if file_record:
                stored_count = 1

        _log_and_record(
            run_id,
            f"[Process {file_index}/{total_files}] ✓ Completed: stored {stored_count} file(s)",
            LogLevel.INFO,
        )

        return {
            "success": True,
            "message_id": message_id,
            "stored": stored_count,
            "processed": 1,
        }

    except Exception as exc:
        _log_and_record(
            run_id,
            f"[Process {file_index}/{total_files}] ✗ Failed: {exc}",
            LogLevel.ERROR,
            details={"error": str(exc), "file": file_name},
        )
        raise


@task(name="process_files_orchestrator")
async def process_files(
    initial_data: Dict[str, Any], pending_files: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Orchestrate file processing using two-phase approach:
    Phase 1: Download all files SEQUENTIALLY with ONE Telethon client (avoids session conflicts)
    Phase 2: Process files IN PARALLEL (extract, upload, checksum, DB recording)
    """
    if not pending_files:
        return {"processed": 0, "stored": 0, "messages": 0}

    config = SourceConfig(**initial_data["config"])
    run_id = initial_data["run_id"]

    selected_files = pending_files[:MAX_FILES_PER_RUN]
    if len(pending_files) > MAX_FILES_PER_RUN:
        _log_and_record(
            run_id,
            (
                f"Limiting run to first {MAX_FILES_PER_RUN} files out of "
                f"{len(pending_files)} pending for debugging"
            ),
            LogLevel.WARNING,
        )

    total_planned = len(selected_files)

    # Estimate total sizes for better timeout planning
    estimated_total_mb = sum(
        (file.get("size", 0) or 0) / 1024 / 1024 for file in selected_files
    )

    _log_and_record(
        run_id,
        f"Processing {total_planned} files (estimated {estimated_total_mb:.1f} MB total)",
    )

    # Create shared temp directory
    temp_dir = tempfile.TemporaryDirectory()

    try:
        # ===== PHASE 1: Sequential Download (ONE Telethon client) =====
        _log_and_record(
            run_id,
            f"Phase 1: Downloading {total_planned} files sequentially (avoids session conflicts)...",
        )

        try:
            # Call the download function directly (as a coroutine, not as a Prefect task)
            # since we're already inside a Prefect task
            processed_archives = set(initial_data.get("processed_archives", []))

            download_results = await download_files_sequential.fn(
                config_dict=initial_data["config"],
                run_id=run_id,
                selected_files=selected_files,
                temp_dir_path=temp_dir.name,
                processed_archives=processed_archives,
            )
        except asyncio.TimeoutError:
            _log_and_record(
                run_id,
                f"Download phase timed out after {DOWNLOAD_TASK_BASE_TIMEOUT}s. "
                f"Consider increasing DOWNLOAD_TASK_BASE_TIMEOUT or reducing MAX_FILES_PER_RUN.",
                LogLevel.ERROR,
            )
            return {"processed": 0, "stored": 0, "messages": 0}

        if not download_results:
            _log_and_record(
                run_id,
                "No files downloaded successfully. Skipping processing phase.",
                LogLevel.WARNING,
            )
            return {"processed": 0, "stored": 0, "messages": 0}

        # ===== PHASE 2: Parallel Post-Processing (NO Telethon clients) =====
        _log_and_record(
            run_id,
            f"Phase 2: Processing {len(download_results)} downloaded files in parallel...",
        )

        # Submit all downloaded files as separate Prefect tasks
        futures = []
        for idx, (file_item, local_path) in enumerate(download_results, 1):
            future = process_downloaded_file.submit(
                config_dict=initial_data["config"],
                run_id=run_id,
                file_item=file_item,
                local_path=local_path,
                temp_dir_path=temp_dir.name,
                file_index=idx,
                total_files=len(download_results),
            )
            futures.append((idx, file_item, future))

        _log_and_record(
            run_id,
            f"Waiting for {len(futures)} processing tasks to complete...",
        )

        # Wait for all tasks and collect results
        results = []
        for idx, file_item, future in futures:
            try:
                result = future.result()
                results.append(result)

                if result.get("success"):
                    stored = result.get("stored", 0)
                    if stored > 0:
                        update_run_counts(run_id, files_processed=idx)
            except asyncio.TimeoutError:
                _log_and_record(
                    run_id,
                    f"Processing task [{idx}/{len(download_results)}] timed out after {PROCESS_FILE_TIMEOUT}s",
                    LogLevel.ERROR,
                    details={
                        "message_id": file_item["message_id"],
                        "file_name": file_item["file_name"],
                    },
                )
                results.append(
                    {
                        "success": False,
                        "reason": "timeout",
                        "message_id": file_item["message_id"],
                    }
                )
            except Exception as exc:
                # Task failed after all retries
                _log_and_record(
                    run_id,
                    f"Processing task [{idx}/{len(download_results)}] failed permanently: {exc}",
                    LogLevel.ERROR,
                    details={
                        "message_id": file_item["message_id"],
                        "file_name": file_item["file_name"],
                        "error": str(exc),
                    },
                )
                results.append(
                    {
                        "success": False,
                        "reason": "task_failed",
                        "message_id": file_item["message_id"],
                    }
                )

        # Aggregate results
        successful = [r for r in results if r.get("success")]
        stored_files = sum(r.get("stored", 0) for r in successful)
        message_ids = set(
            r.get("message_id") for r in successful if r.get("message_id")
        )

        failed_count = len(results) - len(successful)

        _log_and_record(
            run_id,
            (
                f"Processing complete: {len(successful)}/{len(results)} successful, "
                f"{stored_files} files stored total, {failed_count} failed"
            ),
            LogLevel.INFO if failed_count == 0 else LogLevel.WARNING,
        )

        return {
            "processed": len(successful),
            "stored": stored_files,
            "messages": len(message_ids),
        }

    finally:
        temp_dir.cleanup()


@task
def finalize_run(
    initial_data: Dict[str, Any],
    results: Dict[str, Any],
    error: Optional[str] = None,
    cancelled: bool = False,
):
    run_id = initial_data["run_id"]
    config = SourceConfig(**initial_data["config"])

    # Determine status based on cancellation flag
    if cancelled:
        status = ScrapeStatus.CANCELLED
    elif error is None:
        status = ScrapeStatus.COMPLETED
    else:
        status = ScrapeStatus.FAILED

    mark_run_complete(run_id, status=status, notes=error)

    with SessionLocal() as db:
        source = db.query(Source).filter(Source.id == config.id).first()
        if source:
            if error is None and not cancelled:
                source.last_scraped_at = datetime.now(timezone.utc)
                source.total_files_downloaded = (
                    source.total_files_downloaded or 0
                ) + results.get("stored", 0)
                source.total_messages_scraped = (
                    source.total_messages_scraped or 0
                ) + results.get("messages", 0)
            db.commit()

    if cancelled:
        _log_and_record(run_id, "Scrape run cancelled by user", LogLevel.WARNING)
    elif error:
        _log_and_record(run_id, f"Scrape run failed: {error}", LogLevel.ERROR)
    else:
        _log_and_record(
            run_id,
            f"Scrape run completed successfully. Stored {results.get('stored', 0)} file(s)",
            LogLevel.INFO,
        )


@flow(
    name="telegram_scraper_flow",
    task_runner=None,  # Use default task runner
    retries=0,
)
def telegram_scraper_flow(source_id: str):
    concurrency_tag = f"telegram-scraper-source-{source_id}"
    initial_data = None
    logger = get_run_logger()

    try:
        # Enforce per-source concurrency limit
        with concurrency(concurrency_tag, occupy=1):
            logger.info(f"Acquired concurrency slot for source {source_id}")

            # Initialize run INSIDE the concurrency context
            initial_data = initialize_run(source_id)

            try:
                pending_files = collect_new_files(initial_data)
                results = process_files(initial_data, pending_files)

                # Finalize before releasing the concurrency slot
                finalize_run(initial_data, results)

            except CancelledRun:
                # Handle manual cancellation explicitly
                logger.warning(f"Run manually cancelled for source {source_id}")

                if initial_data:
                    finalize_run(
                        initial_data,
                        {"processed": 0, "stored": 0, "messages": 0},
                        error="Run cancelled by user",
                        cancelled=True,
                    )
                raise  # Re-raise to ensure proper flow state

            except Exception as exc:
                if initial_data:
                    finalize_run(
                        initial_data,
                        {"processed": 0, "stored": 0, "messages": 0},
                        error=str(exc),
                    )
                raise

    except CancelledRun:
        # Outer catch to ensure cleanup even if cancellation happens during setup
        logger.warning(f"Flow cancelled during initialization for source {source_id}")
        if initial_data:
            mark_run_complete(
                initial_data["run_id"],
                status=ScrapeStatus.CANCELLED,
                notes="Cancelled by user during initialization",
            )
        raise
