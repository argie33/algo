"""Regression test: scripts/validate_memory.py's check_structure() used plain substring
checks ("tested" in text / "verified" in text) to decide whether a memory makes a
tested/verified claim needing evidence. Those substrings also match inside "untested"/
"unverified" - a memory honestly documenting the ABSENCE of verification got flagged as an
unbacked positive claim, the opposite of what it actually says. Live-reproduced on
stop_loss_guardian_terraform_apply_unverified_20260906.md, which blocked commits repo-wide
(this check runs against the whole memory dir, not just staged files) despite making no
positive tested/verified claim at all.

Fixed by switching to word-boundary regex, which naturally excludes the "un-" prefix.
"""

from pathlib import Path

from scripts.validate_memory import check_structure

UNVERIFIED_CLAIM = """---
name: example_memory
description: "example"
metadata:
  type: project
---

Terraform apply status against live AWS is unverified - this sandbox has no AWS credentials,
so apply status could not be confirmed from the repo alone. Still open, not resolved.
"""


def test_unverified_claim_is_not_flagged_as_unbacked_positive_claim() -> None:
    issues = check_structure(Path("example_memory.md"), UNVERIFIED_CLAIM)

    assert issues == []


def test_bare_positive_tested_claim_with_no_evidence_is_still_flagged() -> None:
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
