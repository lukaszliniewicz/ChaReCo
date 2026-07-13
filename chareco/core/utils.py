"""Filesystem scanning and content-serialization helpers."""

from __future__ import annotations

import fnmatch
import logging
import os
import re
import shutil
import time
from collections.abc import Iterator, Sequence
from pathlib import Path, PurePosixPath


logger = logging.getLogger(__name__)

DEFAULT_MAX_FILE_BYTES = 1_000_000
DEFAULT_MAX_TOTAL_BYTES = 20_000_000
_SAMPLE_SIZE = 8_192

_BINARY_SUFFIXES = frozenset({
    ".7z", ".avi", ".bin", ".bmp", ".bz2", ".class", ".db", ".dll", ".doc",
    ".docx", ".dylib", ".exe", ".flac", ".gif", ".gz", ".ico", ".jar", ".jpeg",
    ".jpg", ".lock", ".m4a", ".mkv", ".mov", ".mp3", ".mp4", ".msi", ".o",
    ".odp", ".ods", ".odt", ".ogg", ".otf", ".pdf", ".pyd", ".pyc", ".rar",
    ".so", ".sqlite", ".tar", ".tif", ".tiff", ".ttf", ".wav", ".webp", ".wmv",
    ".woff", ".woff2", ".xls", ".xlsx", ".xz", ".zip",
})
_GIT_FILENAMES = frozenset({".gitignore", ".gitattributes", ".gitmodules"})
_TEXT_BOMS = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff", b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")


def _normalise_path(path: str | Path) -> str:
    """Return a relative path in portable POSIX form."""
    value = os.fspath(path).replace("\\", "/")
    if value in {"", "."}:
        return ""
    return value[2:] if value.startswith("./") else value.strip("/")


def _matches_glob(relative_path: str, patterns: Sequence[str]) -> bool:
    path = _normalise_path(relative_path)
    name = PurePosixPath(path).name
    for raw_pattern in patterns:
        pattern = _normalise_path(raw_pattern)
        if not pattern:
            continue
        if (
            (pattern.endswith("/*") and path == pattern[:-2])
            or
            fnmatch.fnmatchcase(path, pattern)
            or fnmatch.fnmatchcase(name, pattern)
            or PurePosixPath(path).match(pattern)
        ):
            return True
    return False


def _matches_extension(filename: str, extensions: Sequence[str]) -> bool:
    """Support .py, py, and *.py entries without making filtering surprising."""
    lowered = filename.casefold()
    for extension in extensions:
        rule = extension.strip().casefold()
        if not rule:
            continue
        if rule.startswith("*"):
            if fnmatch.fnmatchcase(lowered, rule):
                return True
            continue
        if not rule.startswith("."):
            rule = f".{rule}"
        if lowered.endswith(rule):
            return True
    return False


def _normalise_rules(rules: Sequence[str] | None) -> tuple[str, ...]:
    """Accept both API sequences and the comma-separated form advertised by the UI."""
    return tuple(
        token
        for rule in rules or ()
        for token in re.split(r"[,\s]+", rule.strip())
        if token
    )


def is_git_related(path: str | Path) -> bool:
    """Match actual Git metadata names, not arbitrary paths containing '.git'."""
    candidate = Path(path)
    return candidate.name == ".git" or candidate.name.casefold() in _GIT_FILENAMES


def is_binary(file_path: str | Path) -> bool:
    """Use a suffix fast path and a small byte sample for unknown formats."""
    path = Path(file_path)
    if path.suffix.casefold() in _BINARY_SUFFIXES or path.name == ".DS_Store":
        return True
    try:
        with path.open("rb") as handle:
            sample = handle.read(_SAMPLE_SIZE)
    except OSError:
        return True
    if not sample or sample.startswith(_TEXT_BOMS):
        return False
    return b"\x00" in sample


def _should_skip_directory(
    directory: Path,
    relative_path: str,
    *,
    ignore_git: bool,
    exclude_patterns: Sequence[str],
) -> bool:
    if directory.is_symlink():
        return True
    if ignore_git and directory.name == ".git":
        return True
    return _matches_glob(relative_path, exclude_patterns)


def _iter_files(
    root_path: str | Path,
    *,
    ignore_git: bool,
    exclude_patterns: Sequence[str],
) -> Iterator[tuple[Path, str]]:
    """Yield safe regular files deterministically while pruning excluded trees."""
    root = Path(root_path).resolve()
    if ignore_git and root.name == ".git":
        return
    for current_root, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current = Path(current_root)
        relative_root = _normalise_path(current.relative_to(root))

        directory_names[:] = sorted(
            name
            for name in directory_names
            if not _should_skip_directory(
                current / name,
                f"{relative_root}/{name}" if relative_root else name,
                ignore_git=ignore_git,
                exclude_patterns=exclude_patterns,
            )
        )

        for filename in sorted(file_names):
            file_path = current / filename
            if file_path.is_symlink():
                continue
            relative_path = _normalise_path(file_path.relative_to(root))
            if ignore_git and is_git_related(filename):
                continue
            if _matches_glob(relative_path, exclude_patterns):
                continue
            yield file_path, relative_path


def should_exclude(
    path: str | Path,
    ignore_git: bool,
    exclude_license: bool,
    exclude_readme: bool,
    exclude_folders: Sequence[str] | None = None,
) -> bool:
    """Compatibility helper used by callers that filter a relative file path."""
    filename = Path(path).name
    lowered = filename.casefold()
    if ignore_git and is_git_related(filename):
        return True
    if exclude_license and lowered in {"license", "license.txt", "license.md"}:
        return True
    if exclude_readme and lowered in {"readme", "readme.txt", "readme.md"}:
        return True
    return _matches_glob(_normalise_path(path), exclude_folders or ())


def _passes_file_filters(
    relative_path: str,
    *,
    include: Sequence[str],
    exclude: Sequence[str],
    ignore_git: bool,
    exclude_license: bool,
    exclude_readme: bool,
    exclude_patterns: Sequence[str],
) -> bool:
    if should_exclude(
        relative_path,
        ignore_git,
        exclude_license,
        exclude_readme,
        exclude_patterns,
    ):
        return False
    filename = PurePosixPath(relative_path).name
    if exclude and _matches_extension(filename, exclude):
        return False
    return not include or _matches_extension(filename, include)


def read_text_file(file_path: str | Path, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> str | None:
    """Read a bounded text file using supported Unicode encodings."""
    file_path = Path(file_path)
    try:
        if file_path.stat().st_size > max_file_bytes or is_binary(file_path):
            return None
        with file_path.open("rb") as handle:
            raw = handle.read(max_file_bytes + 1)
        if len(raw) > max_file_bytes:
            logger.info("Skipping file that exceeded the size limit while reading: %s", file_path)
            return None
    except OSError as error:
        logger.warning("Could not read %s: %s", file_path, error)
        return None

    if raw.startswith((b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")):
        encodings = ("utf-32", "utf-8-sig")
    elif raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings = ("utf-16", "utf-8-sig")
    else:
        encodings = ("utf-8-sig",)
    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    logger.warning("Skipping non-UTF text file: %s", file_path)
    return None


def convert_notebook_to_markdown(file_path: str | Path) -> str | None:
    try:
        import jupytext

        notebook = jupytext.read(file_path)
        return jupytext.writes(notebook, fmt="md")
    except Exception as error:  # jupytext provides several exception types
        logger.warning("Could not convert notebook %s: %s", file_path, error)
        return None


def get_structure(
    path: str | Path,
    only_dirs: bool = False,
    exclude: Sequence[str] | None = None,
    include: Sequence[str] | None = None,
    ignore_git: bool = True,
    exclude_license: bool = True,
    exclude_readme: bool = False,
    exclude_folders: Sequence[str] | None = None,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> str:
    """Return a deterministic, filtered directory tree without following symlinks."""
    root = Path(path).resolve()
    exclude = _normalise_rules(exclude)
    include = _normalise_rules(include)
    patterns = _normalise_rules(exclude_folders)
    structure: list[str] = []

    if ignore_git and root.name == ".git":
        return ""

    for current_root, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current = Path(current_root)
        relative_root = _normalise_path(current.relative_to(root))
        level = 0 if not relative_root else len(PurePosixPath(relative_root).parts)
        indent = "│   " * max(level - 1, 0) + "├── "
        structure.append(f"{indent}{current.name}/")

        directory_names[:] = sorted(
            name
            for name in directory_names
            if not _should_skip_directory(
                current / name,
                f"{relative_root}/{name}" if relative_root else name,
                ignore_git=ignore_git,
                exclude_patterns=patterns,
            )
        )
        if only_dirs:
            continue

        subindent = "│   " * level + "├── "
        for filename in sorted(file_names):
            file_path = current / filename
            relative_path = _normalise_path(file_path.relative_to(root))
            if file_path.is_symlink() or not _passes_file_filters(
                relative_path,
                include=include,
                exclude=exclude,
                ignore_git=ignore_git,
                exclude_license=exclude_license,
                exclude_readme=exclude_readme,
                exclude_patterns=patterns,
            ):
                continue
            try:
                oversized = file_path.stat().st_size > max_file_bytes
            except OSError:
                continue
            if oversized or is_binary(file_path):
                continue
            structure.append(f"{subindent}{filename}")
    return "\n".join(structure)


def concatenate_files(
    path: str | Path,
    exclude: Sequence[str] | None = None,
    include: Sequence[str] | None = None,
    ignore_git: bool = True,
    exclude_license: bool = True,
    exclude_readme: bool = False,
    exclude_folders: Sequence[str] | None = None,
    read_files: bool = True,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> tuple[str, dict[str, int], dict[str, str]]:
    """Serialize eligible files, with bounded output and deterministic ordering."""
    exclude = _normalise_rules(exclude)
    include = _normalise_rules(include)
    patterns = _normalise_rules(exclude_folders)
    content: list[str] = []
    file_positions: dict[str, int] = {}
    file_contents: dict[str, str] = {}
    current_position = 0
    total_bytes = 0
    current_directory: str | None = None

    for file_path, relative_path in _iter_files(
        path, ignore_git=ignore_git, exclude_patterns=patterns
    ):
        if not _passes_file_filters(
            relative_path,
            include=include,
            exclude=exclude,
            ignore_git=ignore_git,
            exclude_license=exclude_license,
            exclude_readme=exclude_readme,
            exclude_patterns=patterns,
        ):
            continue

        try:
            oversized = file_path.stat().st_size > max_file_bytes
        except OSError:
            continue
        if oversized:
            logger.info("Skipping oversized file: %s", relative_path)
            continue

        if not read_files:
            if not is_binary(file_path):
                file_positions[relative_path] = 0
            continue

        if file_path.suffix.casefold() == ".ipynb":
            file_content = convert_notebook_to_markdown(file_path)
        else:
            file_content = read_text_file(file_path, max_file_bytes)
        if file_content is None:
            continue

        encoded_size = len(file_content.encode("utf-8"))
        if total_bytes + encoded_size > max_total_bytes:
            logger.info("Reached output budget; remaining files were skipped.")
            content.append("\n[Output limit reached; remaining files were skipped.]\n")
            break

        directory = PurePosixPath(relative_path).parent.as_posix()
        if directory == ".":
            directory = ""
        if directory != current_directory:
            header = f"\n---{directory + '/' if directory else '/'}---\n"
            content.append(header)
            current_position += len(header)
            current_directory = directory

        filename = PurePosixPath(relative_path).name
        file_header = f"\n--{relative_path}--\n"
        content.append(file_header)
        file_positions[relative_path] = current_position
        current_position += len(file_header)
        content.append(file_content)
        file_contents[relative_path] = file_content
        current_position += len(file_content)
        total_bytes += encoded_size

    return "".join(content), file_positions, file_contents


def concatenate_folder_files(folder_path: str, file_contents: dict[str, str]) -> str:
    """Concatenate a folder and all descendants, preserving relative paths."""
    folder = _normalise_path(folder_path)
    selected = [
        (path, content)
        for path, content in sorted(file_contents.items())
        if not folder or path == folder or path.startswith(f"{folder}/")
    ]
    if not selected:
        return "No text files in this folder."
    return "\n\n".join(f"--{path}--\n{content}" for path, content in selected)


def safe_remove(path: str | Path) -> None:
    """Best-effort cleanup for temporary analysis directories."""
    target = Path(path)
    for attempt in range(3):
        if not target.exists():
            return
        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        except OSError as error:
            logger.warning("Cleanup attempt %s failed for %s: %s", attempt + 1, target, error)
            time.sleep(0.2)
    if target.exists():
        logger.error("Could not remove temporary path: %s", target)
