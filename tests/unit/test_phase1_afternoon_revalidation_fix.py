"""Test Phase 1 afternoon re-validation fix (2026-08-02).

ISSUE: Phase 1 checked for pipeline_context in ("AFTERNOON", "EVENING") but
pipeline_context was set to ("MORNING", "INTRADAY", "EOD"). This meant the
afternoon re-validation was dead code - never executed.

FIX: Changed line 658 to check for ("INTRADAY", "EOD") which are the actual
context values assigned for afternoon/evening hours.

This test verifies the fix exists in the code.
"""

import re


def test_phase1_afternoon_revalidation_uses_correct_context():
    """Verify that Phase 1 checks for correct pipeline_context values for afternoon re-validation."""
    with open("algo/orchestrator/phase1_data_freshness.py", "r") as f:
        content = f.read()

    # Verify the fix: should check ("INTRADAY", "EOD") not ("AFTERNOON", "EVENING")
    # Look for the pattern that was fixed
    pattern = r'if pipeline_context in \("INTRADAY", "EOD"\):'
    assert re.search(pattern, content), (
        "Phase 1 afternoon re-validation should check for ('INTRADAY', 'EOD') contexts. "
        "This was fixed to handle the fact that pipeline_context is only ever set to "
        "'MORNING', 'INTRADAY', or 'EOD', not 'AFTERNOON'/'EVENING'. "
        "Without this fix, afternoon price validation was dead code."
    )

    # Verify the old buggy pattern is NOT in the code
    buggy_pattern = r'if pipeline_context in \("AFTERNOON", "EVENING"\):'
    assert not re.search(buggy_pattern, content), (
        "Phase 1 should NOT check for ('AFTERNOON', 'EVENING') contexts since those "
        "values are never assigned to pipeline_context. The fix should have changed this."
    )

    # Verify the comment explaining the fix is present
    assert "FIXED 2026-08-02" in content or "Changed to check" in content, (
        "Phase 1 should have a comment documenting the fix for pipeline_context values"
    )


def test_phase1_pipeline_context_assignment_matches_validation():
    """Verify that assigned pipeline_context values match what is validated."""
    with open("algo/orchestrator/phase1_data_freshness.py", "r") as f:
        content = f.read()

    # Find where pipeline_context is assigned
    assignment_pattern = r'pipeline_context = "EOD" if.*else "MORNING" if.*else "INTRADAY"'
    assert re.search(assignment_pattern, content), (
        "Phase 1 should assign pipeline_context to exactly ('MORNING', 'INTRADAY', 'EOD')"
    )

    # Find where it's used for afternoon validation
    validation_pattern = r'if pipeline_context in \("INTRADAY", "EOD"\):'
    assert re.search(validation_pattern, content), (
        "Phase 1 should validate today's prices for INTRADAY and EOD contexts"
    )


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
