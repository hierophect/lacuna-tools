#!/usr/bin/env python3
"""Command-line compiler for Lacuna Deck Language 0.5.0."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import Optional, Sequence

try:
    from .compiler import compile_paths
except ImportError:
    from compiler import compile_paths


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile Lacuna Deck Language 0.5.0")
    parser.add_argument("primary_file", metavar="FILE", help="final Deck source file")
    parser.add_argument(
        "-f",
        "--prior-files",
        metavar="PRIOR_FILE",
        nargs="+",
        help="earlier source files, in compilation order",
    )
    parser.add_argument(
        "-i",
        "--issues-only",
        action="store_true",
        help="validate without writing compiled JSON",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="show source records on standard error",
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="show a traceback for an unexpected compiler failure",
    )
    parser.add_argument(
        "-l",
        "--list-infos",
        action="store_true",
        help="show the ordered files being compiled",
    )
    return parser


def _show_inputs(paths: Sequence[Path], verbose: bool, list_infos: bool) -> None:
    for path in paths:
        if list_infos:
            print(f"{path}: info: compiling source", file=sys.stderr)
        if not verbose:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            print(f"{path}:{line_number}: info: {line}", file=sys.stderr)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_argument_parser().parse_args(argv)
    paths = [Path(item) for item in (args.prior_files or [])]
    paths.append(Path(args.primary_file))
    _show_inputs(paths, args.verbose, args.list_infos)
    try:
        result = compile_paths(paths)
    except Exception:
        print("error: unexpected internal compiler failure", file=sys.stderr)
        if args.debug:
            traceback.print_exc(file=sys.stderr)
        return 1
    for diagnostic in result.diagnostics:
        print(diagnostic.format(), file=sys.stderr)
    if result.has_errors:
        return 1
    if not args.issues_only:
        json.dump(result.document, sys.stdout, ensure_ascii=False, indent=4)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
