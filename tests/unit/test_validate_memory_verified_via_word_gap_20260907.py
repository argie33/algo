"""Regression test: scripts/validate_memory.py's check_structure() only recognized the exact
adjacent substring "verified via" as evidence of a shown verification method. Real writeups
often put a few words between the verb and "via" (e.g. "Verified landed via `git show HEAD
--stat`", "confirmed via `grep`/`hasattr` immediately after each Edit call") - genuine
git-command-backed verification that got flagged "no test method shown" anyway because "via"
wasn't immediately adjacent to "verified"/"confirmed". Live-reproduced on
halt_cancels_pending_entry_orders_fixed_20260907.md, which blocked commits repo-wide.

Fixed by allowing up to a few words between "verified"/"confirmed" and "via", not requiring
them adjacent. Same false-positive class already fixed twice before for this function
(2026-08-11 exact-substring test-method check, 2026-09-04 pass-count adjacency check).
"""

from pathlib import Path

from scripts.validate_memory import check_structure

REAL_WORLD_PHRASING = """---
name: example_memory
description: "example"
metadata:
  type: project
---

Verified landed via `git show HEAD --stat` after the merge. Also confirmed via `grep`/`hasattr`
immediately after each Edit call showing 0 matches.
"""


def test_verified_landed_via_phrasing_is_not_flagged_unverified() -> None:
    issues = check_structure(Path("example_memory.md"), REAL_WORLD_PHRASING)

    assert issues == []


def test_confirmed_via_phrasing_is_not_flagged_unverified() -> None:
    content = """---
name: example_memory
description: "example"
metadata:
  type: project
---

Confirmed correct via `git diff --stat` showing zero changes after the fix.
"""
    issues = check_structure(Path("example_memory.md"), content)

    assert issues == []


def test_bare_verified_claim_with_no_evidence_is_still_flagged() -> None:
    content = """---
name: example_memory
description: "example"
metadata:
  type: project
---

This was verified working.
"""
    issues = check_structure(Path("example_memory.md"), content)

    assert any("no test method shown" in issue for issue in issues)
