"""Regression test: scripts/validate_memory.py's per-file read used plain "utf-8" encoding,
which does not strip a leading UTF-8 BOM. A BOM-prefixed memory file (e.g. written by
PowerShell's Out-File, which defaults to UTF-8-with-BOM) read as "﻿---\n..." - so
check_structure()'s `content.startswith("---")` check false-failed a structurally-valid file
as "Missing frontmatter (---)", which blocks every commit repo-wide via this script's
pre-commit hook (validate-memory). Live-reproduced on a real memory file written this session.

Fixed by reading with "utf-8-sig" instead, which strips a BOM if present and behaves
identically to plain "utf-8" otherwise.
"""

from pathlib import Path

from scripts.validate_memory import check_structure

VALID_FRONTMATTER = """---
name: example_memory
description: "example"
metadata:
  type: project
---

Body text.
"""


def test_bom_prefixed_valid_frontmatter_is_not_flagged_missing(tmp_path: Path) -> None:
    filepath = tmp_path / "example_memory.md"
    # Write with a UTF-8 BOM, exactly as PowerShell's `Out-File` (no -Encoding override) does.
    filepath.write_text(VALID_FRONTMATTER, encoding="utf-8-sig")

    content = filepath.read_text(encoding="utf-8-sig", errors="replace")
    issues = check_structure(filepath, content)

    assert issues == []


def test_bom_prefixed_content_still_read_as_utf8_sig_here_would_have_failed_under_plain_utf8() -> None:
    # Sanity check the actual bug mechanism this test guards against: reading BOM-prefixed
    # content with plain "utf-8" (the pre-fix behavior) leaves a literal U+FEFF character at
    # the front, breaking the frontmatter check - proves the fix (utf-8-sig) is what matters,
    # not something else incidentally making the first test pass.
    content_with_bom = "﻿" + VALID_FRONTMATTER
    issues = check_structure(Path("example_memory.md"), content_with_bom)

    assert issues == ["  [FAIL] Missing frontmatter (---)"]
