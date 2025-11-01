import hashlib
import tarfile
import zipfile
from pathlib import Path
from typing import Iterable, List, Optional

try:
    import rarfile  # type: ignore
except ImportError:  # pragma: no cover
    rarfile = None


ARCHIVE_SUFFIXES = {
    ".zip",
    ".rar",
    ".tar",
    ".tgz",
}

ARCHIVE_MULTI_SUFFIXES = {
    ".tar.gz",
    ".tar.bz2",
    ".tar.xz",
}


def sha256_checksum(path: Path, chunk_size: int = 65536) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def is_archive(name: str) -> bool:
    lower_name = name.lower()
    if any(lower_name.endswith(suffix) for suffix in ARCHIVE_MULTI_SUFFIXES):
        return True
    return Path(lower_name).suffix in ARCHIVE_SUFFIXES


def extract_archive(archive_path: Path, destination: Path) -> List[Path]:
    extracted_files: List[Path] = []
    name_lower = archive_path.name.lower()
    suffix = archive_path.suffix.lower()
    destination.mkdir(parents=True, exist_ok=True)

    if suffix == ".zip":
        with zipfile.ZipFile(archive_path, "r") as archive:
            archive.extractall(destination)
            extracted_files = [
                destination / name
                for name in archive.namelist()
                if not name.endswith("/")
            ]
        return extracted_files

    if suffix in {".tar", ".tgz"} or any(
        name_lower.endswith(end) for end in ARCHIVE_MULTI_SUFFIXES
    ):
        mode = "r"
        if name_lower.endswith(".tar.gz"):
            mode = "r:gz"
        elif name_lower.endswith(".tar.bz2"):
            mode = "r:bz2"
        elif name_lower.endswith(".tar.xz"):
            mode = "r:xz"
        with tarfile.open(archive_path, mode) as archive:
            archive.extractall(destination)
            extracted_files = [
                destination / member.name
                for member in archive.getmembers()
                if member.isfile()
            ]
        return extracted_files

    if suffix == ".rar":
        if rarfile is None:
            raise RuntimeError("rarfile package is required to extract .rar archives")
        with rarfile.RarFile(archive_path) as archive:
            archive.extractall(destination)
            extracted_files = [
                destination / info.filename
                for info in archive.infolist()
                if not info.isdir()
            ]
        return extracted_files

    raise ValueError(f"Unsupported archive type: {archive_path.suffix}")


def filter_allowed_files(
    paths: Iterable[Path], allowed_extensions: Optional[Iterable[str]]
) -> List[Path]:
    if not allowed_extensions:
        return list(paths)
    normalized = {ext.lower().lstrip(".") for ext in allowed_extensions}
    filtered: List[Path] = []
    for path in paths:
        if path.suffix:
            if path.suffix.lower().lstrip(".") in normalized:
                filtered.append(path)
        else:
            # Keep files without extension if extensions list allows empty string
            if "" in normalized:
                filtered.append(path)
    return filtered
