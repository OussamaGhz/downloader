import asyncio
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from prefect import flow, task, get_run_logger
from prefect.context import get_run_context
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
)
from app.services.scrape_progress import (
    LogLevel,
    ScrapeStatus,
    create_scrape_run,
    get_processed_file_keys,
    log_event,
    mark_run_complete,
    record_scraped_file,
    update_run_counts,
)
from app.services.storage import get_storage_handler


MAX_FILES_PER_RUN = 10
DOWNLOAD_CONCURRENCY = 3
DOWNLOAD_RETRY_ATTEMPTS = 3
DOWNLOAD_RETRY_BASE_DELAY = 2


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

    _log_and_record(run_id=str(run.id), message="Scrape run initialized")

    return {
        "run_id": str(run.id),
        "config": asdict(config),
        "processed_keys": [(msg_id, file_id) for msg_id, file_id in processed],
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

            new_files.append(
                PendingFile(
                    message_id=message.id,
                    file_id=file_id,
                    file_name=file_name,
                    file_extension=extension,
                    size=message.file.size,
                    date=message.date,
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


@task
async def process_files(
    initial_data: Dict[str, Any], pending_files: List[Dict[str, Any]]
) -> Dict[str, Any]:
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
    _log_and_record(
        run_id,
        (
            f"Processing {total_planned} pending attachment(s) "
            f"with concurrency={DOWNLOAD_CONCURRENCY}"
        ),
    )

    temp_dir = tempfile.TemporaryDirectory()
    storage = get_storage_handler(
        target=TargetEnum(config.target),
        source_id=config.id,
        run_id=run_id,
        target_path=config.target_path,
    )

    processed_files = 0
    stored_files = 0
    message_ids_seen: Set[int] = set()

    client = _build_client(config)
    await _ensure_client_ready(client, config)
    entity = await _resolve_entity(client, config.identifier)

    async def download_item(
        item: Dict[str, Any],
    ) -> Optional[Tuple[Dict[str, Any], Path]]:
        attempt = 0
        delay = DOWNLOAD_RETRY_BASE_DELAY

        while attempt < DOWNLOAD_RETRY_ATTEMPTS:
            try:
                message = await client.get_messages(entity, ids=item["message_id"])
            except (TelethonTimeoutError, asyncio.TimeoutError) as exc:
                attempt += 1
                _log_and_record(
                    run_id,
                    (
                        f"Timeout fetching message {item['message_id']} (attempt {attempt}/"
                        f"{DOWNLOAD_RETRY_ATTEMPTS}): {exc}"
                    ),
                    LogLevel.WARNING,
                )
                await asyncio.sleep(delay)
                delay *= 2
                continue
            except Exception as exc:
                _log_and_record(
                    run_id,
                    f"Failed to fetch message {item['message_id']}: {exc}",
                    LogLevel.ERROR,
                )
                return None

            if not message or not message.file:
                _log_and_record(
                    run_id,
                    f"Skipping message {item['message_id']} with no file",
                    LogLevel.WARNING,
                )
                return None

            destination = (
                Path(temp_dir.name) / f"{item['message_id']}_{item['file_id']}"
            )
            try:
                download_path = await client.download_media(
                    message, file=str(destination)
                )
                return item, Path(download_path)
            except (TelethonTimeoutError, asyncio.TimeoutError) as exc:
                attempt += 1
                _log_and_record(
                    run_id,
                    (
                        f"Timeout downloading message {item['message_id']} (attempt {attempt}/"
                        f"{DOWNLOAD_RETRY_ATTEMPTS}): {exc}"
                    ),
                    LogLevel.WARNING,
                )
                await asyncio.sleep(delay)
                delay *= 2
                continue
            except Exception as exc:
                _log_and_record(
                    run_id,
                    f"Failed to download message {item['message_id']} attachment: {exc}",
                    LogLevel.ERROR,
                )
                return None

        _log_and_record(
            run_id,
            (
                f"Giving up on message {item['message_id']} after "
                f"{DOWNLOAD_RETRY_ATTEMPTS} timeout attempts"
            ),
            LogLevel.ERROR,
        )
        return None

    try:
        current_index = 0
        for batch in _chunked(selected_files, max(1, DOWNLOAD_CONCURRENCY)):
            batch_results = await asyncio.gather(
                *(download_item(item) for item in batch),
                return_exceptions=True,
            )

            for result in batch_results:
                if isinstance(result, Exception):
                    _log_and_record(
                        run_id,
                        f"Unexpected exception during download: {result}",
                        LogLevel.ERROR,
                    )
                    continue
                if result is None:
                    continue

                item, local_path = result
                current_index += 1
                processed_files += 1
                message_ids_seen.add(item["message_id"])
                _log_and_record(
                    run_id,
                    (
                        f"Processing file {current_index}/{total_planned} "
                        f"from message {item['message_id']}: {local_path.name}"
                    ),
                )

                extension = local_path.suffix.lower()
                relative_base = Path(str(item["message_id"]))

                if is_archive(local_path.name):
                    extract_dir = (
                        Path(temp_dir.name)
                        / f"extracted_{item['message_id']}_{item['file_id']}"
                    )
                    try:
                        extracted_paths = extract_archive(local_path, extract_dir)
                    except Exception as exc:  # pragma: no cover - extraction errors
                        _log_and_record(
                            run_id,
                            f"Failed to extract {local_path.name}: {exc}",
                            LogLevel.ERROR,
                        )
                        continue

                    allowed = filter_allowed_files(
                        extracted_paths, config.file_types or ["txt"]
                    )
                    if not allowed:
                        _log_and_record(
                            run_id,
                            f"Archive {local_path.name} did not contain allowed files",
                            LogLevel.INFO,
                        )
                        continue

                    for extracted_file in allowed:
                        relative_name = (
                            relative_base
                            / "extracted"
                            / extracted_file.relative_to(extract_dir)
                        )
                        storage_path = storage.store_file(
                            str(extracted_file),
                            str(relative_name).replace(os.sep, "/"),
                        )
                        checksum = sha256_checksum(extracted_file)
                        file_record = record_scraped_file(
                            run_id=run_id,
                            source_id=config.id,
                            message_id=item["message_id"],
                            file_id=item["file_id"],
                            file_name=extracted_file.name,
                            storage_path=storage_path,
                            file_extension=extracted_file.suffix.lower(),
                            size_bytes=extracted_file.stat().st_size,
                            checksum=checksum,
                            extracted_from=local_path.name,
                            extra_metadata={"archived": True},
                        )
                        if file_record:
                            stored_files += 1
                            update_run_counts(run_id, files_processed=stored_files)
                            _log_and_record(
                                run_id,
                                (
                                    "Stored extracted file "
                                    f"{extracted_file.name} ({stored_files}/{total_planned} stored)"
                                ),
                                LogLevel.INFO,
                            )
                            _log_and_record(
                                run_id,
                                "DB record created",
                                LogLevel.DEBUG,
                                details={
                                    "id": str(file_record.id),
                                    "run_id": str(file_record.run_id),
                                    "source_id": str(file_record.source_id),
                                    "message_id": file_record.message_id,
                                    "file_id": file_record.file_id,
                                    "file_name": file_record.file_name,
                                    "storage_path": file_record.storage_path,
                                    "file_extension": file_record.file_extension,
                                    "size_bytes": file_record.size_bytes,
                                    "checksum": file_record.checksum,
                                    "extracted_from": file_record.extracted_from,
                                },
                            )
                    continue

                normalized_ext = extension.lstrip(".")
                if (
                    config.allowed_extensions
                    and normalized_ext not in config.allowed_extensions
                ):
                    _log_and_record(
                        run_id,
                        f"Skipping file {local_path.name} (extension not allowed)",
                        LogLevel.INFO,
                    )
                    continue

                relative_name = relative_base / local_path.name
                
                storage_path = storage.store_file(
                    str(local_path), str(relative_name).replace(os.sep, "/")
                )
                checksum = sha256_checksum(local_path)
                file_record = record_scraped_file(
                    run_id=run_id,
                    source_id=config.id,
                    message_id=item["message_id"],
                    file_id=item["file_id"],
                    file_name=local_path.name,
                    storage_path=storage_path,
                    file_extension=extension,
                    size_bytes=local_path.stat().st_size,
                    checksum=checksum,
                )
                if file_record:
                    stored_files += 1
                    update_run_counts(run_id, files_processed=stored_files)
                    _log_and_record(
                        run_id,
                        (
                            f"Stored file {local_path.name} "
                            f"({stored_files}/{total_planned} stored)"
                        ),
                    )
                    _log_and_record(
                        run_id,
                        "DB record created",
                        LogLevel.DEBUG,
                        details={
                            "id": str(file_record.id),
                            "run_id": str(file_record.run_id),
                            "source_id": str(file_record.source_id),
                            "message_id": file_record.message_id,
                            "file_id": file_record.file_id,
                            "file_name": file_record.file_name,
                            "storage_path": file_record.storage_path,
                            "file_extension": file_record.file_extension,
                            "size_bytes": file_record.size_bytes,
                            "checksum": file_record.checksum,
                            "extracted_from": file_record.extracted_from,
                        },
                    )
    finally:
        await client.disconnect()
        temp_dir.cleanup()

    return {
        "processed": processed_files,
        "stored": stored_files,
        "messages": len(message_ids_seen),
    }


@task
def finalize_run(
    initial_data: Dict[str, Any], results: Dict[str, Any], error: Optional[str] = None
):
    run_id = initial_data["run_id"]
    config = SourceConfig(**initial_data["config"])

    status = ScrapeStatus.COMPLETED if error is None else ScrapeStatus.FAILED
    mark_run_complete(run_id, status=status, notes=error)

    with SessionLocal() as db:
        source = db.query(Source).filter(Source.id == config.id).first()
        if source:
            if error is None:
                source.last_scraped_at = datetime.now(timezone.utc)
                source.total_files_downloaded = (
                    source.total_files_downloaded or 0
                ) + results.get("stored", 0)
                source.total_messages_scraped = (
                    source.total_messages_scraped or 0
                ) + results.get("messages", 0)
            db.commit()

    if error:
        _log_and_record(run_id, f"Scrape run failed: {error}", LogLevel.ERROR)
    else:
        _log_and_record(
            run_id,
            f"Scrape run completed successfully. Stored {results.get('stored', 0)} file(s)",
            LogLevel.INFO,
        )


@flow
def telegram_scraper_flow(source_id: str):
    initial_data = initialize_run(source_id)

    try:
        pending_files = collect_new_files(initial_data)
        results = process_files(initial_data, pending_files)
        finalize_run(initial_data, results)
    except Exception as exc:
        finalize_run(
            initial_data, {"processed": 0, "stored": 0, "messages": 0}, error=str(exc)
        )
        raise
