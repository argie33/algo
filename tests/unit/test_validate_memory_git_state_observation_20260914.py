"""Regression test: scripts/validate_memory.py's check_structure() required a numeric pass
count alongside a shown command to accept a "tested"/"verified" claim as backed by evidence -
fine for a pytest-result writeup, but a git-state observation ("`git diff HEAD -- <path>`
showed the file missing X while `git show HEAD:<path>` has it intact") has no pass count at
all despite being just as concrete. Live-reproduced on
specialized_py_working_tree_stale_revert_risk_20260914.md, which blocked commits repo-wide.

Fixed by accepting a shown `git diff`/`git show`/`git log`/`git blame` command as self-
sufficient evidence on its own, same evidentiary bar as this function's other shown-command
carve-outs (pytest result line, "verified via `cmd`").
"""

from pathlib import Path

from scripts.validate_memory import check_structure

REAL_WORLD_PHRASING = """---
name: example_memory
description: "example"
metadata:
  type: project
---

Observed 2026-09-14: `git diff HEAD -- some/file.py` in the shared main working tree showed
the on-disk file missing a check function that HEAD (`git show HEAD:some/file.py`) has
intact. This was tested and merged already at HEAD - the working tree is just stale.
"""


def test_git_diff_show_observation_is_not_flagged_unverified() -> None:
    issues = check_structure(Path("example_memory.md"), REAL_WORLD_PHRASING)

    assert issues == []


def test_bare_tested_claim_with_no_evidence_is_still_flagged() -> None:
    content = """---
name: example_memory
description: "example"
metadata:
  type: project
---

This was tested and works.
"""
    issues = check_structure(Path("example_memory.md"), content)

    assert any("no test method shown" in issue for issue in issues)
