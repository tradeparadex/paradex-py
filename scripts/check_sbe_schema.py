#!/usr/bin/env python3
"""Fail when the vendored SBE schema has drifted from the upstream one.

paradex_py/api/sbe/paradex_1_0.xml is a published copy of the schema the
Paradex servers encode with, which is maintained upstream, outside this repo.
The copy is not byte-identical on purpose: its prose is curated for a public
repo. That prose is the XML comments and the description attributes. Everything
else is the schema and must match exactly.

This compares the two structurally: every element, every attribute except
description (including sinceVersion), and every text value, in order. So a
field added, removed, reordered, retyped or re-versioned upstream shows up here.
A description counts only for whether it marks the field DEPRECATED, because
that marker is the one thing the codec generator reads from it.

It does not see prose, so it cannot tell you the public header (version
history, Released date) needs updating; do that by hand when it fails.

Usage:
    # against a copy of the upstream file
    uv run python scripts/check_sbe_schema.py --upstream-file path/to/paradex_1_0.xml

    # against a git checkout of the upstream repo; fetches, then reads
    # <ref>:<path>, with the path taken from --upstream-path or
    # $SBE_SCHEMA_UPSTREAM_PATH
    uv run python scripts/check_sbe_schema.py --upstream-git <checkout> --upstream-path <path>

Exit status: 0 in sync, 1 drifted, 2 the upstream schema could not be read.

When it fails, sync by copying the upstream file over the vendored one,
re-applying the public prose edits (git diff shows them), updating the header,
then regenerating codec.py (see generate_sbe_decoder.py) and rerunning this
until it passes.
"""

import argparse
import difflib
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

VENDORED = Path(__file__).resolve().parent.parent / "paradex_py" / "api" / "sbe" / "paradex_1_0.xml"


def canonical(xml_text: str) -> list[str]:
    """One line per element: tag, sorted attributes and text, whitespace-normalised.

    ElementTree's default parser drops comments. Descriptions are reduced to
    whether they mark the element DEPRECATED.
    """
    root = ET.fromstring(xml_text.encode())
    lines: list[str] = []

    def walk(elem: ET.Element, depth: int) -> None:
        attrs = dict(elem.attrib)
        description = attrs.pop("description", None)
        if description is not None and description.lstrip().startswith("DEPRECATED"):
            attrs["deprecated"] = "true"
        attr_text = " ".join(f"{k}={' '.join(v.split())!r}" for k, v in sorted(attrs.items()))
        text = " ".join((elem.text or "").split())
        lines.append(f"{'  ' * depth}<{elem.tag} {attr_text}> {text}".rstrip())
        for child in elem:
            walk(child, depth + 1)

    walk(root, 0)
    return lines


def read_from_git(checkout: Path, ref: str, path: str, fetch: bool) -> str:
    remote, _, branch = ref.partition("/")
    if fetch and branch:
        # Fetch the branch the ref names, so a stale remote-tracking ref is
        # never what gets compared.
        subprocess.run(["git", "-C", str(checkout), "fetch", "--quiet", remote, branch], check=True)
    return subprocess.run(
        ["git", "-C", str(checkout), "show", f"{ref}:{path}"], check=True, capture_output=True, text=True
    ).stdout


def compare(vendored: str, upstream: str) -> list[str]:
    return list(
        difflib.unified_diff(canonical(upstream), canonical(vendored), "upstream", "paradex-py", lineterm="", n=1)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--upstream-file", type=Path, help="path to the upstream paradex_1_0.xml")
    source.add_argument("--upstream-git", type=Path, help="path to a git checkout of the upstream repo")
    parser.add_argument(
        "--upstream-path",
        default=os.environ.get("SBE_SCHEMA_UPSTREAM_PATH"),
        help="schema path inside the upstream repo (default $SBE_SCHEMA_UPSTREAM_PATH)",
    )
    parser.add_argument("--ref", default="origin/main", help="upstream ref to compare with (default origin/main)")
    parser.add_argument("--no-fetch", action="store_true", help="do not fetch the upstream checkout first")
    args = parser.parse_args()

    try:
        if args.upstream_git:
            if not args.upstream_path:
                parser.error("--upstream-git needs --upstream-path or $SBE_SCHEMA_UPSTREAM_PATH")
            upstream = read_from_git(args.upstream_git, args.ref, args.upstream_path, fetch=not args.no_fetch)
            where = f"{args.upstream_git}@{args.ref}"
        else:
            upstream = args.upstream_file.read_text()
            where = str(args.upstream_file)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Cannot read the upstream schema: {exc}", file=sys.stderr)
        sys.exit(2)

    diff = compare(VENDORED.read_text(), upstream)
    if diff:
        print(f"SBE schema drift: {VENDORED.name} differs from {where} (prose ignored)")
        print("\n".join(diff))
        sys.exit(1)
    print(f"OK: {VENDORED.name} matches {where} (prose ignored)")


if __name__ == "__main__":
    main()
