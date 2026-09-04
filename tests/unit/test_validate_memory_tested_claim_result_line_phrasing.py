"""Regression test: scripts/validate_memory.py's check_structure() required a "tested"/
"verified" claim to show a digit immediately adjacent to "passed" (e.g. "7 passed") before
accepting it as backed by evidence. Real writeups more often phrase results as "N tests ...
still pass" with other words in between - a false positive that blocked commits repo-wide
(this check runs against the whole memory dir, not just staged files) for claims genuinely
backed by a named test file and a pass count. Live-reproduced on
debt_for_roic_confirmed_debt_free_zero_fallback_20260904.md and
sec_xbrl_status_20260904_eod.md, both of which named a real test file and pass count but were
flagged "no test method shown" until this fix.

Fixed by widening the fallback regex to also match a digit followed by "pass"/"passed"/
"passing" within the same sentence, not just immediately adjacent.
"""

from pathlib import Path

from scripts.validate_memory import check_structure

REAL_WORLD_PHRASING = """---
name: example_memory
description: "example"
metadata:
  type: project
---

Code-complete, unit-tested (`tests/unit/test_example_fix_20260904.py`, 6 tests), mypy clean,
312 existing debt/roic/roce/quality_metrics tests still pass.
"""


def test_tests_still_pass_phrasing_is_not_flagged_unverified() -> None:
    issues = check_structure(Path("example_memory.md"), REAL_WORLD_PHRASING)

    assert issues == []


def test_bare_tested_claim_with_no_evidence_is_still_flagged() -> None:
    content = """---
name: example_memory
description: "example"
metadata:
  type: project
---

This was tested and verified working.
"""
    issues = check_structure(Path("example_memory.md"), content)

    assert any("no test method shown" in issue for issue in issues)
