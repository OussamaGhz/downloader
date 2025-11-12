import hashlib
import tarfile
import zipfile
import re
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


def extract_archive(
    archive_path: Path, destination: Path, passwords: Optional[List[str]] = None
) -> List[Path]:
    """
    Extract archive to destination directory.

    Args:
        archive_path: Path to the archive file
        destination: Directory to extract to
        passwords: Optional list of passwords to try for password-protected archives

    Returns:
        List of extracted file paths

    Raises:
        RuntimeError: If archive is password-protected and no valid password provided
        ValueError: If archive type is unsupported
    """
    extracted_files: List[Path] = []
    name_lower = archive_path.name.lower()
    suffix = archive_path.suffix.lower()
    destination.mkdir(parents=True, exist_ok=True)

    passwords = passwords or []

    if suffix == ".zip":
        with zipfile.ZipFile(archive_path, "r") as archive:
            # Check if password protected
            for info in archive.infolist():
                if info.flag_bits & 0x1:  # Password protected
                    success = False

                    for pwd in passwords:
                        try:
                            archive.setpassword(pwd.encode("utf-8"))
                            archive.extractall(destination)
                            extracted_files = [
                                destination / name
                                for name in archive.namelist()
                                if not name.endswith("/")
                            ]
                            success = True
                            break
                        except (RuntimeError, zipfile.BadZipFile):
                            continue

                    if not success:
                        raise RuntimeError(
                            f"ZIP archive is password-protected. Tried {len(passwords)} password(s), none worked."
                        )
                    return extracted_files

            # Not password protected
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
            if archive.needs_password():
                success = False

                for pwd in passwords:
                    try:
                        archive.setpassword(pwd)
                        archive.extractall(destination)
                        extracted_files = [
                            destination / info.filename
                            for info in archive.infolist()
                            if not info.isdir()
                        ]
                        success = True
                        break
                    except (rarfile.BadRarFile, rarfile.PasswordRequired):
                        continue

                if not success:
                    raise RuntimeError(
                        f"RAR archive is password-protected. Tried {len(passwords)} password(s), none worked."
                    )
                return extracted_files

            # Not password protected
            archive.extractall(destination)
            extracted_files = [
                destination / info.filename
                for info in archive.infolist()
                if not info.isdir()
            ]
        return extracted_files

    raise ValueError(f"Unsupported archive type: {archive_path.suffix}")


def extract_password_from_message(message: str) -> List[str]:
    """
    Extract potential passwords from a message.
    Returns a list of password candidates to try.

    Common patterns:
    - password: pass123
    - Password = pass123
    - pass: pass123
    - pwd: pass123
    - Пароль: pass123 (Russian)
    """
    if not message:
        return []

    candidates = []

    # Pattern 1: "password:" or "pass:" or "pwd:" followed by the password
    patterns = [
        r"(?i)password[:\s=]+(\S+)",
        r"(?i)pass[:\s=]+(\S+)",
        r"(?i)pwd[:\s=]+(\S+)",
        r"(?i)пароль[:\s=]+(\S+)",  # Russian
        r"(?i)contraseña[:\s=]+(\S+)",  # Spanish
        r"(?i)mot de passe[:\s=]+(\S+)",  # French
    ]

    for pattern in patterns:
        matches = re.findall(pattern, message)
        candidates.extend(matches)

    # Pattern 2: Look for standalone words that might be passwords
    # (after common password keywords, grab quoted strings)
    quoted_patterns = [
        r'(?i)password[:\s=]+["\']([^"\']+)["\']',
        r'(?i)pass[:\s=]+["\']([^"\']+)["\']',
    ]

    for pattern in quoted_patterns:
        matches = re.findall(pattern, message)
        candidates.extend(matches)

    # Remove duplicates while preserving order
    seen = set()
    unique_candidates = []
    for pwd in candidates:
        pwd_stripped = pwd.strip()
        if pwd_stripped and pwd_stripped not in seen:
            seen.add(pwd_stripped)
            unique_candidates.append(pwd_stripped)

    return unique_candidates


def extract_archive_recursive(
    archive_path: Path,
    destination: Path,
    passwords: Optional[List[str]] = None,
    depth: int = 0,
    max_depth: int = 5,
) -> List[Path]:
    """
    Recursively extract archive and any nested archives within it.

    Args:
        archive_path: Path to the archive file
        destination: Base directory to extract to
        passwords: Optional list of passwords to try for password-protected archives
        depth: Current recursion depth (internal use)
        max_depth: Maximum recursion depth to prevent infinite loops

    Returns:
        List of all extracted file paths (including files from nested archives)

    Raises:
        RuntimeError: If archive is password-protected and no valid password provided
        ValueError: If archive type is unsupported
    """
    if depth >= max_depth:
        raise RuntimeError(f"Maximum extraction depth ({max_depth}) reached")

    all_extracted_files: List[Path] = []

    # Create extraction directory with archive name
    archive_name_without_ext = archive_path.stem
    # Handle multi-part extensions like .tar.gz
    for multi_ext in ARCHIVE_MULTI_SUFFIXES:
        if archive_path.name.lower().endswith(multi_ext):
            archive_name_without_ext = archive_path.name[: -len(multi_ext)]
            break

    extract_dir = destination / f"{archive_name_without_ext}_extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)

    # Extract the archive
    extracted_files = extract_archive(archive_path, extract_dir, passwords)
    all_extracted_files.extend(extracted_files)

    # Check for nested archives and extract them recursively
    nested_archives = [f for f in extracted_files if is_archive(f.name)]

    for nested_archive in nested_archives:
        try:
            # Extract nested archive in its parent directory
            nested_parent = nested_archive.parent
            nested_extracted = extract_archive_recursive(
                nested_archive, nested_parent, passwords, depth + 1, max_depth
            )
            all_extracted_files.extend(nested_extracted)

            # Remove the nested archive file after successful extraction
            nested_archive.unlink()
            all_extracted_files.remove(nested_archive)
        except Exception as e:
            # Log error but continue with other files
            # The nested archive will remain as a file
            pass

    return all_extracted_files


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
