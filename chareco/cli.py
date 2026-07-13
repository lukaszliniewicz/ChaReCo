"""Headless repository-context command-line interface."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from chareco.core.models import AnalysisOptions
from chareco.core.service import run_analysis


def _rules(value: str) -> tuple[str, ...]:
    return tuple(rule for rule in re.split(r"[,\s]+", value.strip()) if rule)


def _mib(value: str) -> int:
    parsed = float(value)
    if parsed <= 0 or parsed > 1024:
        raise argparse.ArgumentTypeError("must be greater than 0 and no more than 1024")
    return int(parsed * 1024 * 1024)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create bounded, searchable-ready context from a repository or local folder."
    )
    parser.add_argument("source", help="Repository URL or local folder path")
    parser.add_argument("--local", action="store_true", help="Treat source as a local folder")
    parser.add_argument("--branch", help="Remote branch or tag to clone")
    parser.add_argument("--include", default="", help="Comma- or space-separated extensions to include")
    parser.add_argument("--exclude", default="", help="Comma- or space-separated extensions to exclude")
    parser.add_argument("--exclude-pattern", action="append", default=[], help="Glob pattern to exclude")
    parser.add_argument("--include-git", action="store_true", help="Include Git metadata files")
    parser.add_argument("--include-license", action="store_true", help="Include LICENSE files")
    parser.add_argument("--exclude-readme", action="store_true", help="Exclude README files")
    parser.add_argument("--structure-only", action="store_true", help="Do not concatenate file content")
    parser.add_argument("--snapshot", action="store_true", help="Analyze a temporary local-folder snapshot")
    parser.add_argument("--max-file-mib", type=_mib, default=1024 * 1024, help="Per-file limit (default: 1)")
    parser.add_argument("--max-output-mib", type=_mib, default=20 * 1024 * 1024, help="Total output limit (default: 20)")
    parser.add_argument(
        "--pat-env",
        metavar="VARIABLE",
        help="Read a GitHub PAT from this environment variable; never pass tokens on the command line.",
    )
    parser.add_argument("--output", type=Path, help="Write output to this UTF-8 text file instead of stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.local and not Path(args.source).is_dir():
        raise SystemExit(f"Not a directory: {args.source}")
    patterns = [pattern for value in args.exclude_pattern for pattern in _rules(value)]
    options = AnalysisOptions(
        source_path=args.source,
        is_local=args.local,
        include_extensions=_rules(args.include),
        exclude_extensions=_rules(args.exclude),
        exclude_patterns=tuple(patterns),
        include_git=args.include_git,
        include_license=args.include_license,
        exclude_readme=args.exclude_readme,
        concatenate=not args.structure_only,
        copy_local_folder=args.snapshot,
        branch=args.branch,
        max_file_bytes=args.max_file_mib,
        max_total_bytes=args.max_output_mib,
    )
    pat = os.environ.get(args.pat_env) if args.pat_env else None

    def progress(message: str, _percent: int) -> None:
        print(message, file=sys.stderr)

    result = run_analysis(options, pat=pat, progress=progress)
    if args.output:
        args.output.write_text(result.full_text, encoding="utf-8")
    else:
        print(result.full_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
