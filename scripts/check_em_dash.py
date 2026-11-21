"""Refuse new em dashes: Tony's house rule, no U+2014 in anything he reads.

Only the lines a change adds are checked, so files that already carry one (tests proving
the publish kit strips them, older docs) never block unrelated work. Code that must name
the character writes the escape "\\u2014".

    python3 scripts/check_em_dash.py --staged              # the pre-commit hook
    python3 scripts/check_em_dash.py --base origin/master  # CI: everything a branch adds
"""
from __future__ import annotations

import argparse
import subprocess
import sys

EM_DASH = "\u2014"
FIX = ("No em dashes (house rule). Use a comma, colon or period; in code that must name the "
       "character, write the escape \\u2014.")


def added_lines(diff_text):
    """(file, new line number, text) for every line a unified diff adds. A file's header
    ends at its first hunk, so an added line that itself starts with "++" stays a line."""
    path, number, in_header = "?", 0, False
    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            path, in_header = "?", True
        elif in_header and raw.startswith("+++ "):
            path = raw[6:] if raw.startswith("+++ b/") else raw[4:]
        elif raw.startswith("@@"):
            in_header = False
            number = int(raw.split("+", 1)[1].split(" ", 1)[0].split(",")[0])
        elif in_header:
            continue
        elif raw.startswith("+"):
            yield path, number, raw[1:]
            number += 1
        elif raw.startswith(" "):
            number += 1


def offenders(diff_text):
    return [(path, number, text) for path, number, text in added_lines(diff_text) if EM_DASH in text]


def diff(staged, base):
    cmd = ["git", "-c", "core.quotePath=false", "diff", "--no-color", "--no-ext-diff", "-U0",
           "--src-prefix=a/", "--dst-prefix=b/", "--diff-filter=ACMR"]
    cmd += ["--cached"] if staged else [f"{base}...HEAD"]
    return subprocess.run(cmd, capture_output=True, check=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def main(argv=None):
    parser = argparse.ArgumentParser(description="refuse em dashes in the lines a change adds")
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--staged", action="store_true", help="check what is staged (pre-commit)")
    which.add_argument("--base", help="check everything HEAD adds since its merge base with BASE")
    args = parser.parse_args(argv)
    found = offenders(diff(args.staged, args.base))
    for path, number, text in found:
        print(f"{path}:{number}: em dash: {text.strip()[:100]}", file=sys.stderr)
    if found:
        print(FIX, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
