"""Pure analysis service shared by the GUI worker and command-line interface."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dulwich import porcelain

from chareco.core.models import AnalysisOptions, AnalysisResult
from chareco.core.utils import concatenate_files, get_structure, safe_remove


class AnalysisCancelled(Exception):
    """Raised internally when a caller asks the analysis service to stop."""


def display_source(source: str) -> str:
    """Remove URL user info before placing a source in output or logs."""
    parsed = urlsplit(source)
    if not parsed.scheme:
        return source
    hostname = parsed.hostname or ""
    netloc = hostname if not parsed.port else f"{hostname}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, ""))


def _clone_repository(options: AnalysisOptions, destination: str, pat: str | None) -> str:
    source = options.source_path.strip()
    clone_kwargs: dict[str, object] = {"depth": 1}
    parsed = urlsplit(source)
    if parsed.scheme in {"http", "https"} and (parsed.username or parsed.password):
        raise ValueError("Credentials embedded in repository URLs are not supported; use the PAT field instead.")
    if options.branch:
        clone_kwargs["branch"] = options.branch

    if pat:
        if parsed.scheme != "https" or (parsed.hostname or "").casefold() != "github.com":
            raise ValueError("A Personal Access Token may only be used with an HTTPS github.com URL.")
        clone_kwargs.update({"username": "x-access-token", "password": pat})

    repository = porcelain.clone(source, destination, **clone_kwargs)
    return repository.head().hex()


def run_analysis(
    options: AnalysisOptions,
    *,
    pat: str | None = None,
    progress: Callable[[str, int], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> AnalysisResult:
    """Run one bounded analysis without any Qt dependency."""
    progress = progress or (lambda _message, _value: None)
    is_cancelled = is_cancelled or (lambda: False)
    temporary_directory: str | None = None

    def check_cancelled() -> None:
        if is_cancelled():
            raise AnalysisCancelled

    try:
        check_cancelled()
        if options.is_local:
            folder_path = options.source_path
            if options.copy_local_folder:
                temporary_directory = tempfile.mkdtemp(prefix="chareco-")
                source_folder = Path(folder_path)
                folder_path = str(Path(temporary_directory) / source_folder.name)
                progress("Creating local snapshot…", 10)
                shutil.copytree(
                    source_folder,
                    folder_path,
                    symlinks=True,
                    ignore=shutil.ignore_patterns(".git"),
                    dirs_exist_ok=True,
                )
            revision = "local working tree"
        else:
            temporary_directory = tempfile.mkdtemp(prefix="chareco-")
            folder_path = temporary_directory
            progress("Cloning repository…", 10)
            revision = _clone_repository(options, folder_path, pat)

        check_cancelled()
        progress("Generating folder structure…", 45)
        structure = get_structure(
            folder_path,
            exclude=options.exclude_extensions,
            include=options.include_extensions,
            ignore_git=not options.include_git,
            exclude_license=not options.include_license,
            exclude_readme=options.exclude_readme,
            exclude_folders=options.exclude_patterns,
            max_file_bytes=options.max_file_bytes,
        )

        check_cancelled()
        progress("Scanning files…", 70)
        retain_snapshot_content = options.is_local and options.copy_local_folder
        concatenated_content, file_positions, file_contents = concatenate_files(
            folder_path,
            exclude=options.exclude_extensions,
            include=options.include_extensions,
            ignore_git=not options.include_git,
            exclude_license=not options.include_license,
            exclude_readme=options.exclude_readme,
            exclude_folders=options.exclude_patterns,
            read_files=options.concatenate or retain_snapshot_content,
            max_file_bytes=options.max_file_bytes,
            max_total_bytes=options.max_total_bytes,
        )

        check_cancelled()
        metadata = {
            "Source": display_source(options.source_path),
            "Revision": revision,
            "Mode": "local folder" if options.is_local else "remote repository",
            "File limit": f"{options.max_file_bytes:,} bytes per file",
            "Output limit": f"{options.max_total_bytes:,} bytes",
        }
        manifest = "Context manifest:\n" + "\n".join(
            f"- {name}: {value}" for name, value in metadata.items()
        )
        full_text = f"{manifest}\n\nFolder structure:\n{structure}\n"
        if options.concatenate:
            full_text += f"\nConcatenated content:\n{concatenated_content}"
        progress("Finalizing results…", 95)
        return AnalysisResult(
            full_text=full_text,
            folder_structure=structure,
            file_positions=file_positions,
            file_contents=file_contents,
            metadata=metadata,
        )
    finally:
        if temporary_directory:
            safe_remove(temporary_directory)
