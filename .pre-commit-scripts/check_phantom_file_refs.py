#!/usr/bin/env python
"""Blocks reintroducing references to files that were deliberately deleted from this repo.

This is the exact bug class CLAUDE.md documents happening 3 separate times
(start_dashboard_dev.py, check_system_health.py, steering/OPERATIONS.md /
QUICKSTART_LOCAL.md): a file gets deleted, but a stale reference to it survives
in a comment/doc/log message elsewhere, and later gets suggested again as if it
were real - each time discovered only by a manual full-repo search months later.

Add an entry here the next time a phantom-file reference is found and fixed, so
this hook catches any *new* reintroduction of that same name going forward. This
is deliberately NOT a general "does this path exist" checker - false positives
on legitimately-referenced-but-not-yet-created paths (e.g. planned files named in
a design doc) would make the hook noisy and get it disabled. It only flags names
already proven to be phantom-reference-prone.
"""

import subprocess
import sys

# name -> pointer to what to say instead, matching CLAUDE.md's existing fixes.
KNOWN_PHANTOM_FILES = {
    "start_dashboard_dev.py": "does not exist and never did - point at the Quick Start section of CLAUDE.md instead",
    "check_system_health.py": "was deleted - point at scripts/monitor_data_staleness.py instead",
    "steering/OPERATIONS.md": "was deliberately deleted (commit 6e81a267c) - point at steering/GOVERNANCE.md or CLAUDE.md instead",
    "QUICKSTART_LOCAL.md": "never existed - point at CLAUDE.md's Quick Start section instead",
}


def main() -> int:
    # encoding="utf-8" + errors="replace" (not the default text=True, which decodes with
    # the platform locale encoding - cp1252 on Windows) - a staged diff containing any byte
    # sequence invalid in that codec (e.g. 0x8f, seen live in a concurrent session's shared
    # checkout) otherwise crashes the subprocess text-decoding thread and leaves .stdout as
    # None, which then raised AttributeError: 'NoneType' object has no attribute 'splitlines'
    # here instead of a decode error - blocking every commit repo-wide, not just the one
    # that introduced the byte. This check only substring-matches known phantom filenames,
    # so a replacement char in place of an undecodable byte can never mask a real match.
    diff = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--diff-filter=ACM"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout

    failures = []
    current_file = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            continue
        if current_file == ".pre-commit-scripts/check_phantom_file_refs.py":
            continue  # this file's own deny-list necessarily contains the phantom names
        if not line.startswith("+") or line.startswith("+++"):
            continue
        added_text = line[1:]
        for name, guidance in KNOWN_PHANTOM_FILES.items():
            if name in added_text:
                failures.append(f"  {current_file}: references '{name}' - {guidance}")

    if failures:
        print(
            "Phantom-file reference check failed - these filenames were deliberately "
            "removed from this repo and should not be reintroduced in comments/docs/logs:\n" + "\n".join(failures),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
